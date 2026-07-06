from __future__ import annotations

import structlog

from app.llm.factory import get_provider
from app.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)


async def intake_node(state: PipelineState) -> dict:
    """Node 1: structured LLM extraction of substances from the SDS/test-report text
    (PDF -> text already done by the API layer before the graph is invoked)."""
    provider = get_provider()
    result = await provider.extract(state["raw_text"])
    logger.info("intake_node_done", product_id=state["product_id"], substance_count=len(result.substances))
    return {
        "product_name": result.product_name or state.get("filename", "Unknown product"),
        "manufacturer": result.manufacturer or "",
        "extracted_substances": [s.model_dump() for s in result.substances],
    }
