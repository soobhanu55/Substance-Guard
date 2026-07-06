from __future__ import annotations

from functools import lru_cache

from google import genai

from app.config import get_settings


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; cannot compute embeddings")
    return genai.Client(api_key=settings.gemini_api_key)


async def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embeds a batch of texts with Gemini's text-embedding-004. `task_type` should be
    RETRIEVAL_DOCUMENT when embedding corpus chunks and RETRIEVAL_QUERY when embedding
    a user question, per Gemini's asymmetric embedding guidance."""
    settings = get_settings()
    client = _client()
    from google.genai import types

    response = await client.aio.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [e.values for e in response.embeddings]


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text], task_type="RETRIEVAL_QUERY"))[0]
