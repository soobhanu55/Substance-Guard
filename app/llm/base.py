from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import ExtractionResult


class ExtractionProvider(ABC):
    @abstractmethod
    async def extract(self, document_text: str) -> ExtractionResult:
        """Extracts substances (name, CAS, concentration, unit, component) from raw
        SDS/test-report text. Not yet graph-checked or guardrail-checked."""
        raise NotImplementedError
