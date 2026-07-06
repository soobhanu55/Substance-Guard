from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.pdf.parser import extract_text
from app.pipeline.product_store import get_status
from app.pipeline.runner import run_pipeline

router = APIRouter()


class ScreenResponse(BaseModel):
    product_id: str
    status: str


class ProductStatusResponse(BaseModel):
    product_id: str
    status: str
    report: dict | None = None
    error: str | None = None


@router.post("/screen", response_model=ScreenResponse, status_code=202)
async def screen_document(file: UploadFile, background_tasks: BackgroundTasks):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported.")

    settings = get_settings()
    contents = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=422, detail=f"File exceeds {settings.max_upload_mb}MB limit.")

    try:
        raw_text = extract_text(contents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    product_id = str(uuid.uuid4())
    background_tasks.add_task(run_pipeline, product_id, file.filename, raw_text)
    return ScreenResponse(product_id=product_id, status="processing")


@router.get("/product/{product_id}/status", response_model=ProductStatusResponse)
async def get_product_status(product_id: str):
    entry = await get_status(product_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown product_id.")
    return ProductStatusResponse(product_id=product_id, **entry)


@router.get("/product/{product_id}/report")
async def get_product_report(product_id: str):
    entry = await get_status(product_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown product_id.")
    if entry.get("report") is None:
        raise HTTPException(status_code=409, detail=f"Report not ready yet (status={entry['status']}).")
    return entry["report"]
