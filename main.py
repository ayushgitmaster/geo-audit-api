"""GEO Audit API — FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.api.routes import router
from app.core.config import settings


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "A mini GEO (Generative Engine Optimization) audit API that "
            "scrapes a public webpage, analyses its AI-citation readiness, "
            "and recommends JSON-LD structured data."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow local frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(router, prefix="/api/v1", tags=["GEO Audit"])

    # Serve static frontend
    static_dir = Path(__file__).resolve().parent / "app" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_frontend():
            return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()
