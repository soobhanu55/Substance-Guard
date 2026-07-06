from __future__ import annotations

import asyncio
import json

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import get_settings
from app.llm.base import ExtractionProvider
from app.models import ExtractionResult

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a structured-data extraction engine for supplier safety data \
sheets (SDS) and material test reports. Extract ONLY substances that are explicitly named \
with a stated concentration in the document text. Do not infer, estimate, or guess a \
concentration that is not stated. Do not decide or comment on regulatory compliance -- that \
is a downstream step you have no role in. If a CAS number is not printed in the document, \
leave cas_number null; do not invent one. If a concentration range is given (e.g. "10-15%"), \
use the upper bound and lower extraction_confidence accordingly. Normalize the unit field to \
exactly one of "pct", "ppm", "ppb" based on what the document states."""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "product_name": {"type": "STRING", "nullable": True},
        "manufacturer": {"type": "STRING", "nullable": True},
        "substances": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "cas_number": {"type": "STRING", "nullable": True},
                    "concentration": {"type": "NUMBER"},
                    "unit": {"type": "STRING", "description": "pct, ppm, or ppb"},
                    "component_name": {"type": "STRING"},
                    "extraction_confidence": {"type": "NUMBER"},
                },
                "required": ["name", "concentration", "unit", "component_name", "extraction_confidence"],
            },
        },
    },
    "required": ["substances"],
}


class GeminiExtractionProvider(ExtractionProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set; cannot use llm_provider=gemini")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    async def extract(self, document_text: str) -> ExtractionResult:
        response = None
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=document_text,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=_RESPONSE_SCHEMA,
                        temperature=0,
                    ),
                )
                break
            except genai_errors.ServerError as exc:
                # Transient 5xx (model overloaded) -- worth a short backoff-retry.
                # 429 quota errors are NOT retried here: retrying a quota error just
                # burns time without changing the outcome.
                last_exc = exc
                logger.warning("gemini_transient_error", attempt=attempt, error=str(exc))
                await asyncio.sleep(min(2 ** (attempt + 1), 30))
        if response is None:
            raise last_exc  # noqa: RSE102 -- re-raising the last transient error after retries exhausted
        if not response.text:
            raise RuntimeError("Gemini response contained no text output")

        data = json.loads(response.text)
        result = ExtractionResult.model_validate(data)
        logger.info("extraction_completed", substance_count=len(result.substances))
        return result
