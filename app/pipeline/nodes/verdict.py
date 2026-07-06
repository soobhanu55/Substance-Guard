from __future__ import annotations

import structlog

from app.config import get_settings
from app.guardrails.rules import apply_guardrails
from app.models import GraphMatch, RagCitation, SubstanceVerdict, VerdictStatus
from app.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)

_TO_PCT = {"pct": 1.0, "ppm": 1e-4, "ppb": 1e-7}


def _to_pct(value: float, unit: str) -> float:
    return value * _TO_PCT.get(unit, 1.0)


def _evaluate_threshold(measured_pct: float, threshold_value: float, threshold_unit: str, band_pct: float) -> str:
    """Returns 'compliant' | 'non_compliant' | 'borderline'. band_pct is a RELATIVE
    percentage band around the threshold (e.g. 10 = +/-10% of the threshold value)."""
    threshold_pct = _to_pct(threshold_value, threshold_unit)
    band = threshold_pct * (band_pct / 100.0)
    if measured_pct > threshold_pct + band:
        return "non_compliant"
    if measured_pct >= threshold_pct - band:
        return "borderline"
    return "compliant"


def _build_verdict(match: GraphMatch, citations: list[RagCitation]) -> SubstanceVerdict:
    substance = match.substance
    measured_pct = _to_pct(substance.concentration, substance.unit)

    if not match.found_in_graph:
        return SubstanceVerdict(
            substance_name=substance.name, cas_number=substance.cas_number,
            component_name=substance.component_name, status=VerdictStatus.NEEDS_REVIEW,
            measured_value=substance.concentration, measured_unit=substance.unit,
            explanation="not yet templated", reason_code="not_found_in_graph",
        )

    if match.match_method == "fuzzy_name":
        return SubstanceVerdict(
            substance_name=substance.name, cas_number=substance.cas_number,
            component_name=substance.component_name, status=VerdictStatus.NEEDS_REVIEW,
            measured_value=substance.concentration, measured_unit=substance.unit,
            explanation="not yet templated", reason_code="ambiguous_name_match",
        )

    if not match.thresholds:
        return SubstanceVerdict(
            substance_name=substance.name, cas_number=substance.cas_number,
            component_name=substance.component_name, status=VerdictStatus.NEEDS_REVIEW,
            measured_value=substance.concentration, measured_unit=substance.unit,
            explanation="not yet templated", reason_code="no_threshold_on_record",
        )

    settings = get_settings()
    worst_status = VerdictStatus.COMPLIANT
    cited_threshold = match.thresholds[0]
    reason_code = "within_threshold"

    for t in match.thresholds:
        outcome = _evaluate_threshold(measured_pct, t["value"], t["unit"], settings.borderline_band_pct)
        if outcome == "non_compliant":
            worst_status = VerdictStatus.NON_COMPLIANT
            cited_threshold = t
            reason_code = "exceeds_threshold"
            break
        if outcome == "borderline" and worst_status == VerdictStatus.COMPLIANT:
            worst_status = VerdictStatus.NEEDS_REVIEW
            cited_threshold = t
            reason_code = "borderline_concentration"

    matching_citations = [c for c in citations if c.regulation_name == cited_threshold.get("regulation")] or citations

    return SubstanceVerdict(
        substance_name=substance.name, cas_number=substance.cas_number,
        component_name=substance.component_name, status=worst_status,
        regulation_name=cited_threshold.get("regulation"),
        threshold_value=cited_threshold.get("value"), threshold_unit=cited_threshold.get("unit"),
        measured_value=substance.concentration, measured_unit=substance.unit,
        citations=matching_citations, explanation="not yet templated", reason_code=reason_code,
    )


def _template_explanation(v: SubstanceVerdict) -> str:
    base = (f"Screening result for review: {v.substance_name}"
            + (f" (CAS {v.cas_number})" if v.cas_number else " (no CAS number extracted)")
            + f" in component '{v.component_name}', measured at {v.measured_value}{v.measured_unit}.")
    if v.reason_code == "not_found_in_graph":
        return base + " This substance was not found in the regulatory graph -- cannot confirm compliance or non-compliance; routed to human review."
    if v.reason_code == "ambiguous_name_match":
        return base + " No CAS number was extracted and the substance name matched more than one graph entry -- routed to human review rather than guessed."
    if v.reason_code == "no_threshold_on_record":
        return base + f" Substance is known to the graph but has no recorded threshold under {v.regulation_name or 'any regulation'} -- routed to human review."
    if v.reason_code == "borderline_concentration":
        return base + (f" This is within {get_settings().borderline_band_pct:.0f}% of the {v.regulation_name} "
                        f"threshold of {v.threshold_value}{v.threshold_unit} -- routed to human review as a borderline case.")
    if v.reason_code == "exceeds_threshold":
        return base + f" This exceeds the {v.regulation_name} threshold of {v.threshold_value}{v.threshold_unit}."
    return base + f" This is within the {v.regulation_name} threshold of {v.threshold_value}{v.threshold_unit}."


async def verdict_node(state: PipelineState) -> dict:
    """Node 4: deterministic compare-to-threshold core, followed by the guardrail pass.
    The LLM has no role in deciding COMPLIANT/NON_COMPLIANT/NEEDS_REVIEW -- only the
    unit-normalized numeric comparison and the graph/citation lookups do. Explanation
    text is templated from those same grounded facts (not a second free-form LLM call)
    specifically so there is nothing for the guardrail to have to catch."""
    verdicts: list[dict] = []
    for idx, raw in enumerate(state.get("graph_matches", [])):
        match = GraphMatch.model_validate(raw)
        citations = [RagCitation.model_validate(c) for c in state.get("citations_by_index", {}).get(str(idx), [])]
        verdict = _build_verdict(match, citations)
        verdict = verdict.model_copy(update={"explanation": _template_explanation(verdict)})
        verdict, guardrail_result = apply_guardrails(verdict, match.found_in_graph)
        if guardrail_result.rewritten:
            verdict = verdict.model_copy(update={"explanation": _template_explanation(verdict)})
        verdicts.append(verdict.model_dump())

    logger.info("verdict_node_done", product_id=state["product_id"],
                compliant=sum(1 for v in verdicts if v["status"] == "COMPLIANT"),
                non_compliant=sum(1 for v in verdicts if v["status"] == "NON_COMPLIANT"),
                needs_review=sum(1 for v in verdicts if v["status"] == "NEEDS_REVIEW"))
    return {"verdicts": verdicts}
