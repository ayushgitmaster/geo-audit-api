"""Tests for the GEO Audit API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.anyio
async def test_audit_invalid_url(client: AsyncClient):
    resp = await client.post("/api/v1/audit", json={"url": "not-a-url"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_audit_missing_url(client: AsyncClient):
    resp = await client.post("/api/v1/audit", json={})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_audit_success(client: AsyncClient):
    """Integration test — requires network access."""
    resp = await client.post(
        "/api/v1/audit",
        json={"url": "https://example.com"},
        timeout=30,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "extracted_data" in body
    assert "schema_recommendation" in body
    assert "audit_summary" in body
    assert body["extracted_data"]["url"].rstrip("/") == "https://example.com"


@pytest.mark.anyio
async def test_audit_response_structure(client: AsyncClient):
    """Verify all expected fields are present in a successful response."""
    resp = await client.post(
        "/api/v1/audit",
        json={"url": "https://example.com"},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip("Network unavailable")

    body = resp.json()

    # Extracted data fields
    ed = body["extracted_data"]
    assert "title" in ed
    assert "meta_description" in ed
    assert "headings" in ed
    assert "image_urls" in ed
    assert "word_count" in ed

    # Audit summary fields
    au = body["audit_summary"]
    assert "overall_score" in au
    assert "scores" in au
    assert "recommendations" in au
    assert 0 <= au["overall_score"] <= 100

    # Schema recommendation
    sr = body["schema_recommendation"]
    assert "schema_type" in sr
    assert "json_ld" in sr
    assert sr["json_ld"]["@context"] == "https://schema.org"


@pytest.mark.anyio
async def test_error_response_shape(client: AsyncClient):
    """Error responses must conform to the ErrorResponse schema."""
    resp = await client.post(
        "/api/v1/audit",
        json={"url": "https://this-domain-absolutely-does-not-exist-geo-audit.invalid"},
        timeout=30,
    )
    assert resp.status_code in (502, 504)
    body = resp.json()
    assert body["success"] is False
    assert "error" in body
