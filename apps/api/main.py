"""
Engineering Intelligence Hub — FastAPI Application
===================================================
Entry point for the REST API. Phase-0 provides:
  - /health  — liveness probe
  - /info    — project metadata and configuration summary
  - /ready   — readiness probe (checks component availability)

Full engineering task endpoints (POST /tasks, GET /tasks/{id}, etc.)
will be added in Phase-1 once the retrieval and generation layers
have concrete implementations.
"""

from __future__ import annotations

import platform
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import health
from core.config import settings
from core.logging import configure_logging, get_logger


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: setup on startup, teardown on shutdown."""
    logger.info(
        f"Starting {settings.project_name} v{settings.version} "
        f"[{settings.environment}]"
    )
    # Phase-1: initialise vector store, graph store, embedding model here.
    yield
    logger.info(f"Shutting down {settings.project_name}")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.project_name,
    description=(
        "Task-Aware Energy-Efficient RAG for Software Engineering. "
        "Research platform for optimising quality, cost, latency, energy "
        "and carbon footprint across SDLC tasks."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(health.router, tags=["Health"])


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "message": f"Welcome to {settings.project_name}",
        "docs": "/docs",
        "health": "/health",
        "info": "/info",
    }
