from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class VerdictStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExtractedSubstance(BaseModel):
    name: str
    cas_number: str | None = None
    concentration: float
    unit: str = Field(description="pct | ppm | ppb")
    component_name: str
    extraction_confidence: float = Field(ge=0, le=1)


class ExtractionResult(BaseModel):
    product_name: str | None = None
    manufacturer: str | None = None
    substances: list[ExtractedSubstance] = Field(default_factory=list)


class GraphMatch(BaseModel):
    substance: ExtractedSubstance
    found_in_graph: bool
    resolved_cas_number: str | None = None
    resolved_name: str | None = None
    regulations: list[dict] = Field(default_factory=list)
    thresholds: list[dict] = Field(default_factory=list)
    match_method: str = Field(description="exact_cas | fuzzy_name | none")


class RagCitation(BaseModel):
    text: str
    source_id: str
    regulation_name: str
    clause_id: str | None = None


class SubstanceVerdict(BaseModel):
    substance_name: str
    cas_number: str | None
    component_name: str
    status: VerdictStatus
    regulation_name: str | None = None
    threshold_value: float | None = None
    threshold_unit: str | None = None
    measured_value: float
    measured_unit: str
    citations: list[RagCitation] = Field(default_factory=list)
    explanation: str
    reason_code: str


class ComplianceReport(BaseModel):
    product_id: str
    product_name: str
    overall_status: VerdictStatus
    substance_verdicts: list[SubstanceVerdict]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewQueueItem(BaseModel):
    id: str
    product_id: str
    substance_verdict: SubstanceVerdict
    reason: str
    status: str = "pending"  # pending | approved | rejected
    decided_by: str | None = None
    decided_at: datetime | None = None
