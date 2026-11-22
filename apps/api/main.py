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

import os

# The embedder and reranker are in the local HF cache; without this every model load asks
# huggingface.co for metadata (slow, and the app failed over when the site reset the
# connection, 2026-11-23). Set EIH_ALLOW_HF_DOWNLOAD=1 to let the app download a new model.
if os.environ.get("EIH_ALLOW_HF_DOWNLOAD") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import adaptive, chat, graph, health, ingest, okf, query, results, retrieval, trace_v1
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
    # Warm the embedder and the BM25 index in the background (plan §10.4: one-time loading
    # is never charged to a query). Without this the first chat took 133 s in BM25 indexing
    # (measured 2026-11-23). Status is reported by /status; failures are logged, not hidden.
    import threading

    from apps.api import services
    threading.Thread(target=services.warm_up, daemon=True, name="eih-warm-up").start()
    yield
    logger.info(f"Shutting down {settings.project_name}")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.project_name,
    description=(
        "Task-Aware, Quality-Constrained RAG for Software Engineering: Optimising Quality, "
        "Cost, Latency, Energy and Carbon Footprint (research title restored by WORK_PLAN C18)."
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
app.include_router(ingest.router, tags=["Ingestion"])
app.include_router(retrieval.router, tags=["Retrieval"])
app.include_router(query.router, tags=["Query"])
app.include_router(graph.router, tags=["Knowledge Graph"])
app.include_router(adaptive.router, tags=["Adaptive Retrieval (M3)"])
app.include_router(okf.router)
app.include_router(chat.router)
app.include_router(results.router)
app.include_router(trace_v1.router)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """Contract v1 (§2): /v1 errors use ErrorResponse, never FastAPI's HTTPValidationError
    (and never echo input, paths or config). Other routes keep the FastAPI default."""
    if request.url.path.startswith("/v1/"):
        from apps.api.contract.v1 import ErrorCode
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) or "body" for e in exc.errors()})
        return trace_v1.error_response(trace_v1.request_id(request), 422, ErrorCode.INVALID_REQUEST,
                                       f"Invalid request fields: {', '.join(fields)[:400]}")
    return await request_validation_exception_handler(request, exc)


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
