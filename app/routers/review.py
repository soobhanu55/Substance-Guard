from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.pipeline import review_store
from app.pipeline.runner import resume_pipeline

router = APIRouter()


class ReviewDecisionRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    decided_by: str


@router.get("/review/queue")
async def list_review_queue(status: str | None = "pending"):
    return await review_store.list_items(status=status)


@router.post("/review/{item_id}/decision")
async def decide_review_item(item_id: str, body: ReviewDecisionRequest):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'.")

    item = await review_store.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown review item_id.")

    updated = await review_store.decide(item_id, body.decision, body.decided_by)

    remaining = await review_store.list_items(status="pending")
    still_pending_for_product = [i for i in remaining if i.product_id == item.product_id]
    if not still_pending_for_product:
        await resume_pipeline(item.product_id)

    return updated
