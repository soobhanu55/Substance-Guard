from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.base import ExtractionProvider


@lru_cache(maxsize=1)
def get_provider() -> ExtractionProvider:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicExtractionProvider
        return AnthropicExtractionProvider()
    from app.llm.gemini_provider import GeminiExtractionProvider
    return GeminiExtractionProvider()
