"""API routes for the GEO Audit service."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.models.schemas import (
    AuditRequest,
    AuditResponse,
    ErrorResponse,
)
from app.services.analyzer import analyse
from app.services.schema_generator import generate_schema
from app.services.scraper import scrape_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/audit",
    response_model=AuditResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid URL format"},
        502: {"model": ErrorResponse, "description": "Scraping failed"},
    },
    summary="Run a GEO audit on a public webpage",
    description=(
        "Accepts a public URL, scrapes the page, analyses GEO readiness, "
        "and returns a JSON-LD schema recommendation."
    ),
)
async def run_audit(body: AuditRequest) -> AuditResponse | JSONResponse:
    url = str(body.url)

    def _err(code: int, error: str, detail: str | None = None) -> JSONResponse:
        return JSONResponse(
            status_code=code,
            content=ErrorResponse(error=error, detail=detail).model_dump(),
        )

    # 1. Scrape
    try:
        extracted = await scrape_url(url)
    except httpx.HTTPStatusError as exc:
        return _err(
            status.HTTP_502_BAD_GATEWAY,
            "Upstream HTTP error",
            f"Target returned HTTP {exc.response.status_code}",
        )
    except httpx.TimeoutException:
        return _err(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "Request timed out",
            "Timed out while fetching the target URL",
        )
    except ValueError as exc:
        return _err(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid content",
            str(exc),
        )
    except Exception as exc:
        logger.exception("Scraping error for %s", url)
        return _err(
            status.HTTP_502_BAD_GATEWAY,
            "Scraping failed",
            str(exc),
        )

    # 2. Analyse
    audit_summary = analyse(extracted)

    # 3. Schema recommendation
    schema_rec, llm_used = await generate_schema(extracted)

    return AuditResponse(
        extracted_data=extracted,
        schema_recommendation=schema_rec,
        audit_summary=audit_summary,
        llm_used=llm_used,
    )


@router.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
