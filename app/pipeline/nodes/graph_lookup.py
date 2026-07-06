from __future__ import annotations

import structlog

from app.graph.queries import find_substance_by_name_fuzzy, get_substance_regulations
from app.models import ExtractedSubstance, GraphMatch
from app.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)


async def graph_lookup_node(state: PipelineState) -> dict:
    """Node 2: for each extracted substance, resolve it against the Neo4j regulatory
    graph. Exact CAS match first; conservative fuzzy name match only as a fallback that
    is itself flagged for review, never treated as a confirmed match -- 'never guess'
    starts here, not just in the verdict/guardrail step."""
    matches: list[dict] = []
    for raw in state.get("extracted_substances", []):
        substance = ExtractedSubstance.model_validate(raw)

        if substance.cas_number:
            hit = await get_substance_regulations(substance.cas_number)
            if hit:
                matches.append(GraphMatch(
                    substance=substance, found_in_graph=True,
                    resolved_cas_number=hit["cas_number"], resolved_name=hit["name"],
                    regulations=hit["regulations"], thresholds=hit["thresholds"],
                    match_method="exact_cas",
                ).model_dump())
                continue

        fuzzy = await find_substance_by_name_fuzzy(substance.name)
        if fuzzy:
            # Any name-only match (whether one candidate or several) is inherently less
            # certain than an exact CAS match -- always routed to review downstream
            # (see verdict.py: match_method == "fuzzy_name" forces NEEDS_REVIEW),
            # regardless of how many candidates the fuzzy lookup found.
            hit = await get_substance_regulations(fuzzy["cas_number"])
            matches.append(GraphMatch(
                substance=substance, found_in_graph=True,
                resolved_cas_number=fuzzy["cas_number"], resolved_name=fuzzy["name"],
                regulations=hit["regulations"] if hit else [], thresholds=hit["thresholds"] if hit else [],
                match_method="fuzzy_name",
            ).model_dump())
        else:
            matches.append(GraphMatch(
                substance=substance, found_in_graph=False, match_method="none",
            ).model_dump())

    logger.info("graph_lookup_node_done", product_id=state["product_id"],
                found=sum(1 for m in matches if m["found_in_graph"]), total=len(matches))
    return {"graph_matches": matches}
