from __future__ import annotations

import structlog

from app.models import GraphMatch, RagCitation
from app.pipeline.state import PipelineState
from app.rag.retriever import retrieve

logger = structlog.get_logger(__name__)


async def rag_retrieval_node(state: PipelineState) -> dict:
    """Node 3: for every substance that matched a regulation in the graph, pull the
    citable clause text backing that regulation's threshold from Qdrant (clause-based
    collection, for citation precision -- see tests/accuracy/chunking_eval.py)."""
    citations_by_index: dict[str, list[dict]] = {}
    for idx, raw in enumerate(state.get("graph_matches", [])):
        match = GraphMatch.model_validate(raw)
        if not match.found_in_graph or not match.regulations:
            continue
        substance_citations: list[dict] = []
        for reg in match.regulations:
            reg_name = reg.get("name")
            if not reg_name:
                continue
            query = f"concentration threshold and obligations for {match.substance.name} under {reg_name}"
            hits = await retrieve(query, regulation_name=reg_name, top_k=1)
            substance_citations.extend(
                RagCitation(text=h.text, source_id=h.source_id, regulation_name=h.regulation_name,
                            clause_id=h.clause_id).model_dump()
                for h in hits
            )
        citations_by_index[str(idx)] = substance_citations

    logger.info("rag_retrieval_node_done", product_id=state["product_id"], substances_cited=len(citations_by_index))
    return {"citations_by_index": citations_by_index}
