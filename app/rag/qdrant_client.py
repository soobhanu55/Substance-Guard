from __future__ import annotations

from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from app.config import get_settings

EMBEDDING_DIM = 3072  # gemini-embedding-001


@lru_cache(maxsize=1)
def get_qdrant() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
