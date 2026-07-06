from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.llm.embeddings import embed_texts
from app.rag.chunkers import Chunk, clause_chunks, fixed_window_chunks
from app.rag.qdrant_client import EMBEDDING_DIM, get_qdrant

logger = structlog.get_logger(__name__)

REGULATION_TEXTS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "regulatory_data" / "regulation_texts"

_FILE_TO_REGULATION = {
    "reach_svhc_obligations.txt": "REACH_SVHC",
    "rohs_annex_ii.txt": "ROHS_ANNEX_II",
    "pfas_restriction_background.txt": "PFAS_RESTRICTION_DRAFT",
}


async def _ensure_collection(name: str) -> None:
    qdrant = get_qdrant()
    if not await qdrant.collection_exists(name):
        await qdrant.create_collection(name, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))


async def _embed_and_upsert(collection: str, chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    await _ensure_collection(collection)
    vectors = await embed_texts([c.text for c in chunks], task_type="RETRIEVAL_DOCUMENT")
    qdrant = get_qdrant()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "text": chunk.text,
                "source_id": chunk.source_id,
                "regulation_name": chunk.regulation_name,
                "clause_id": chunk.clause_id,
                "chunk_index": chunk.chunk_index,
                "strategy": chunk.strategy,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    await qdrant.upsert(collection_name=collection, points=points)
    return len(points)


async def ingest_regulation_corpus() -> dict[str, int]:
    settings = get_settings()
    counts = {"clause_chunks": 0, "fixed_chunks": 0}
    for filename, regulation_name in _FILE_TO_REGULATION.items():
        text = (REGULATION_TEXTS_DIR / filename).read_text(encoding="utf-8")
        clauses = clause_chunks(text, source_id=filename, regulation_name=regulation_name)
        fixed = fixed_window_chunks(text, source_id=filename, regulation_name=regulation_name)
        counts["clause_chunks"] += await _embed_and_upsert(settings.qdrant_collection_clauses, clauses)
        counts["fixed_chunks"] += await _embed_and_upsert(settings.qdrant_collection_fixed, fixed)
    logger.info("regulation_corpus_ingested", **counts)
    return counts
