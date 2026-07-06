from __future__ import annotations

import structlog

from app.models import ComplianceReport, SubstanceVerdict, VerdictStatus
from app.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)

_SEVERITY = {VerdictStatus.NON_COMPLIANT: 2, VerdictStatus.NEEDS_REVIEW: 1, VerdictStatus.COMPLIANT: 0}


async def report_node(state: PipelineState) -> dict:
    """Node 5: assemble the structured per-product ComplianceReport. Overall product
    status is the worst-case of its substance verdicts (any NON_COMPLIANT wins; else any
    NEEDS_REVIEW; else COMPLIANT only if every substance was resolved and within threshold)."""
    verdicts = [SubstanceVerdict.model_validate(v) for v in state.get("verdicts", [])]
    overall = VerdictStatus.COMPLIANT
    if verdicts:
        overall = max((v.status for v in verdicts), key=lambda s: _SEVERITY[s])

    report = ComplianceReport(
        product_id=state["product_id"],
        product_name=state.get("product_name", "Unknown product"),
        overall_status=overall,
        substance_verdicts=verdicts,
    )
    logger.info("report_node_done", product_id=state["product_id"], overall_status=overall.value)
    return {"report": report.model_dump(mode="json")}
