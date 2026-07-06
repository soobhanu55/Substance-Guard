from __future__ import annotations

import structlog
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.llm.base import ExtractionProvider
from app.llm.gemini_provider import _SYSTEM_PROMPT
from app.models import ExtractionResult

logger = structlog.get_logger(__name__)

_EXTRACT_TOOL = {
    "name": "extract_substances",
    "description": "Record the substances found in an SDS/test-report document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "product_name": {"type": ["string", "null"]},
            "manufacturer": {"type": ["string", "null"]},
            "substances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "cas_number": {"type": ["string", "null"]},
                        "concentration": {"type": "number"},
                        "unit": {"type": "string", "description": "pct, ppm, or ppb"},
                        "component_name": {"type": "string"},
                        "extraction_confidence": {"type": "number"},
                    },
                    "required": ["name", "concentration", "unit", "component_name", "extraction_confidence"],
                },
            },
        },
        "required": ["substances"],
    },
}


class AnthropicExtractionProvider(ExtractionProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot use llm_provider=anthropic")
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    async def extract(self, document_text: str) -> ExtractionResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_substances"},
            messages=[{"role": "user", "content": document_text}],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        result = ExtractionResult.model_validate(tool_use.input)
        logger.info("extraction_completed", substance_count=len(result.substances))
        return result
