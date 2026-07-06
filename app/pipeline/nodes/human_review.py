from __future__ import annotations

import hashlib

import structlog
from langgraph.types import interrupt

from app.models import ReviewQueueItem, SubstanceVerdict, VerdictStatus
from app.pipeline.review_store import add_item
from app.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)


def _deterministic_item_id(product_id: str, verdict: SubstanceVerdict) -> str:
    """LangGraph re-runs an interrupted node's code from the top on resume, so the
    code before interrupt() (this loop) executes twice. A deterministic id (rather than
    uuid4) makes add_item's upsert idempotent across that replay instead of creating a
    duplicate review-queue entry every time a node resumes."""
    key = f"{product_id}:{verdict.substance_name}:{verdict.component_name}:{verdict.reason_code}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


async def human_review_node(state: PipelineState) -> dict:
    """Node 6: any NEEDS_REVIEW substance is persisted to the review queue. In
    interactive mode (the FastAPI /screen path) the graph genuinely pauses here via
    LangGraph's interrupt() -- resumed later by POST /review/{id}/decision with
    Command(resume=...). In batch/eval mode (accuracy/load-test harnesses) interactive
    is set False so a run of 20-30 documents doesn't block on a human that isn't there;
    review items are still recorded either way."""
    verdicts = [SubstanceVerdict.model_validate(v) for v in state.get("verdicts", [])]
    flagged = [v for v in verdicts if v.status == VerdictStatus.NEEDS_REVIEW]

    item_ids: list[str] = []
    for v in flagged:
        item = ReviewQueueItem(
            id=_deterministic_item_id(state["product_id"], v), product_id=state["product_id"],
            substance_verdict=v, reason=v.reason_code,
        )
        await add_item(item)
        item_ids.append(item.id)

    if flagged and state.get("interactive", True):
        interrupt({
            "product_id": state["product_id"],
            "pending_review_item_ids": item_ids,
            "message": f"{len(flagged)} substance(s) require human review before this product's report is final.",
        })

    logger.info("human_review_node_done", product_id=state["product_id"], flagged=len(flagged))
    return {"review_item_ids": item_ids}
