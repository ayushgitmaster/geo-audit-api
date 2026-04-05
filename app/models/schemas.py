from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


# ── Request ──────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    url: HttpUrl = Field(
        ...,
        description="Public webpage URL to audit",
        examples=["https://stripe.com"],
    )


# ── Extracted page data ─────────────────────────────────────────────

class HeadingItem(BaseModel):
    level: str = Field(..., description="Heading tag, e.g. h1, h2")
    text: str


class ExtractedData(BaseModel):
    url: str
    title: str | None = None
    meta_description: str | None = None
    headings: list[HeadingItem] = []
    image_urls: list[str] = []
    word_count: int = 0
    language: str | None = None


# ── Schema recommendation ───────────────────────────────────────────

class SchemaRecommendation(BaseModel):
    schema_type: str = Field(
        ..., description="Recommended schema.org type, e.g. Organization"
    )
    confidence: float = Field(
        ..., ge=0, le=1, description="Confidence score 0-1"
    )
    reasoning: str = Field(
        ..., description="Why this schema type was chosen"
    )
    json_ld: dict[str, Any] = Field(
        ..., description="Ready-to-use JSON-LD block"
    )


# ── Audit scores ────────────────────────────────────────────────────

class AuditScore(BaseModel):
    category: str
    score: int = Field(..., ge=0, le=100)
    details: str


class GEOAuditSummary(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    scores: list[AuditScore]
    recommendations: list[str]


# ── Full response ───────────────────────────────────────────────────

class AuditResponse(BaseModel):
    success: bool = True
    extracted_data: ExtractedData
    schema_recommendation: SchemaRecommendation
    audit_summary: GEOAuditSummary
    llm_used: bool = Field(
        False, description="Whether an LLM was used for schema generation"
    )


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
