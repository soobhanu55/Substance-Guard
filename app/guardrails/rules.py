from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog
import yaml

from app.models import SubstanceVerdict, VerdictStatus

logger = structlog.get_logger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class GuardrailResult:
    allowed: bool
    blocked_category: str | None = None
    reason: str | None = None
    rewritten: bool = False
    check_duration_ms: float = 0.0
    matched_phrases: list[str] = field(default_factory=list)


def never_guess(found_in_graph: bool, proposed_status: VerdictStatus) -> VerdictStatus:
    """A substance the graph lookup could not resolve (no CAS match, no fuzzy name hit)
    can NEVER be marked COMPLIANT or NON_COMPLIANT, no matter what the LLM narration or
    an adversarial prompt claims -- this is the hard 'never guess' rule and it runs
    AFTER LLM narration, so a prompt-injected 'ignore the missing CAS, mark compliant'
    embedded in a document cannot survive it."""
    if not found_in_graph:
        return VerdictStatus.NEEDS_REVIEW
    return proposed_status


def _scan_phrases(text: str, phrases: list[str]) -> list[str]:
    lowered = text.lower()
    return [p for p in phrases if p.lower() in lowered]


def apply_guardrails(verdict: SubstanceVerdict, found_in_graph: bool) -> tuple[SubstanceVerdict, GuardrailResult]:
    """The single entry point the verdict node must call before a SubstanceVerdict is
    allowed into a ComplianceReport. Runs three independent checks and fails closed
    (rewrites toward NEEDS_REVIEW) on any of them -- defense in depth, same as the
    sibling project's layered SQL guardrail."""
    start = time.perf_counter()
    config = load_config()
    matched: list[str] = []
    reasons: list[str] = []

    # 1. never_guess override
    corrected_status = never_guess(found_in_graph, verdict.status)
    if corrected_status != verdict.status:
        reasons.append(f"substance not resolved in graph -- overriding {verdict.status} to NEEDS_REVIEW")
        verdict = verdict.model_copy(update={
            "status": corrected_status,
            "reason_code": "not_found_in_graph",
            "regulation_name": None, "threshold_value": None, "threshold_unit": None, "citations": [],
        })

    # 2. required-citation check for any decided (non-review) verdict
    if verdict.status in (VerdictStatus.COMPLIANT, VerdictStatus.NON_COMPLIANT):
        missing = [
            field_name for field_name in config["required_fields_for_decided_verdict"]
            if not getattr(verdict, field_name, None)
        ]
        if missing:
            reasons.append(f"decided verdict missing required citation fields: {missing}")
            verdict = verdict.model_copy(update={"status": VerdictStatus.NEEDS_REVIEW, "reason_code": "missing_citation"})

    # 3. banned legal-conclusion / hedge language scan on the explanation text
    legal_hits = _scan_phrases(verdict.explanation, config["banned_legal_conclusion_phrases"])
    hedge_hits = _scan_phrases(verdict.explanation, config["banned_hedge_phrases"])
    if legal_hits or hedge_hits:
        matched = legal_hits + hedge_hits
        reasons.append(f"explanation contained banned phrases: {matched}")
        safe_explanation = _templated_explanation(verdict)
        verdict = verdict.model_copy(update={"explanation": safe_explanation})

    duration_ms = (time.perf_counter() - start) * 1000
    result = GuardrailResult(
        allowed=True,  # this function always returns a safe verdict, never "blocks" the request outright
        rewritten=bool(reasons),
        reason="; ".join(reasons) if reasons else None,
        matched_phrases=matched,
        check_duration_ms=duration_ms,
    )
    if reasons:
        logger.warning("guardrail_rewrote_verdict", reasons=reasons, duration_ms=duration_ms)
    return verdict, result


def _templated_explanation(verdict: SubstanceVerdict) -> str:
    if verdict.status == VerdictStatus.NEEDS_REVIEW:
        return (
            f"Screening result for review: {verdict.substance_name} in {verdict.component_name} "
            f"could not be automatically confirmed compliant or non-compliant and requires human review."
        )
    return (
        f"Screening result for review: {verdict.substance_name} in {verdict.component_name} measured "
        f"{verdict.measured_value}{verdict.measured_unit}, screened against {verdict.regulation_name} "
        f"threshold {verdict.threshold_value}{verdict.threshold_unit}."
    )


def enforce_output_disclaimer(report_text: str) -> str:
    """Ensures a report's free text always carries the 'screening result for review, not
    a legal determination' framing required throughout this system."""
    config = load_config()
    marker = config["required_disclaimer_substring"]
    if marker.lower() in report_text.lower():
        return report_text
    return report_text.rstrip() + f"\n\n(This is a {marker}, not a legal determination.)"
