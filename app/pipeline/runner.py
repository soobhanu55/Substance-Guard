from __future__ import annotations

import structlog
from langgraph.types import Command

from app.pipeline.graph import compiled_graph
from app.pipeline.product_store import set_status

logger = structlog.get_logger(__name__)


async def run_pipeline(product_id: str, filename: str, raw_text: str) -> None:
    await set_status(product_id, "processing")
    try:
        async with compiled_graph() as graph:
            config = {"configurable": {"thread_id": product_id}}
            result = await graph.ainvoke(
                {"product_id": product_id, "filename": filename, "raw_text": raw_text, "interactive": True},
                config=config,
            )
            snapshot = await graph.aget_state(config)
            status = "needs_review" if snapshot.next else "complete"
            await set_status(product_id, status, report=result.get("report"))
    except Exception as exc:  # noqa: BLE001 -- surfaced via GET /product/{id}/status, not swallowed
        logger.error("pipeline_run_failed", product_id=product_id, error=str(exc))
        await set_status(product_id, "error", error=str(exc))


async def resume_pipeline(product_id: str) -> None:
    async with compiled_graph() as graph:
        config = {"configurable": {"thread_id": product_id}}
        result = await graph.ainvoke(Command(resume={"decision": "reviewed"}), config=config)
        await set_status(product_id, "complete", report=result.get("report"))
