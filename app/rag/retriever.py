from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.llm.embeddings import embed_query
from app.rag.qdrant_client import get_qdrant


@dataclass
class Citation:
    text: str
    source_id: str
    regulation_name: str
    clause_id: str | None
    score: float


async def retrieve(query: str, regulation_name: str | None = None, top_k: int = 3,
                    collection: str | None = None) -> list[Citation]:
    """Retrieves the top-k most relevant regulation-text chunks for `query`, optionally
    filtered to one regulation. Defaults to the clause-based collection since verdict
    citations need a clause-precise source; pass collection=settings.qdrant_collection_fixed
    to use the fixed-window index instead (see tests/unit for the head-to-head eval)."""
    settings = get_settings()
    collection = collection or settings.qdrant_collection_clauses
    query_vector = await embed_query(query)

    qdrant_filter = None
    if regulation_name:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        qdrant_filter = Filter(must=[FieldCondition(key="regulation_name", match=MatchValue(value=regulation_name))])

    qdrant = get_qdrant()
    results = await qdrant.query_points(
        collection_name=collection, query=query_vector, query_filter=qdrant_filter, limit=top_k,
    )
    return [
        Citation(
            text=p.payload["text"], source_id=p.payload["source_id"],
            regulation_name=p.payload["regulation_name"], clause_id=p.payload.get("clause_id"),
            score=p.score,
        )
        for p in results.points
    ]
