from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    product_id: str
    filename: str
    raw_text: str
    interactive: bool  # False in batch/eval runs -- skips the interrupt() pause in Node 6

    product_name: str
    manufacturer: str
    extracted_substances: list[dict[str, Any]]  # ExtractedSubstance.model_dump()

    graph_matches: list[dict[str, Any]]  # GraphMatch.model_dump()
    citations_by_index: dict[str, list[dict[str, Any]]]  # str(index) -> [RagCitation.model_dump()]

    verdicts: list[dict[str, Any]]  # SubstanceVerdict.model_dump()
    report: dict[str, Any]  # ComplianceReport.model_dump()
    review_item_ids: list[str]
