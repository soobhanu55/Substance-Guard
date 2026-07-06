from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.graph.client import close_driver
from app.graph.loader import load_regulatory_data
from app.graph.schema import apply_schema
from app.rag.ingest import ingest_regulation_corpus
from app.rag.qdrant_client import get_qdrant
from app.routers import health, review, screen, substances

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await apply_schema()
    await load_regulatory_data()

    settings = get_settings()
    qdrant = get_qdrant()
    if not await qdrant.collection_exists(settings.qdrant_collection_clauses):
        await ingest_regulation_corpus()

    logger.info("startup_complete")
    yield
    await close_driver()


app = FastAPI(title="SubstanceGuard", lifespan=lifespan)

app.include_router(health.router)
app.include_router(screen.router)
app.include_router(substances.router)
app.include_router(review.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=str(request.url), error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
