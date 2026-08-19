"""
Engineering Intelligence Hub — Health & Info Endpoints
"""

from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: str


class SystemInfo(BaseModel):
    python_version: str
    platform: str
    cpu_count: int
    memory_total_gb: float
    memory_available_gb: float


class ComponentStatus(BaseModel):
    vector_store: str
    graph_store: str
    llm_provider: str


class InfoResponse(BaseModel):
    project_name: str
    version: str
    environment: str
    system: SystemInfo
    components: ComponentStatus
    default_model: str
    default_retrieval_strategy: str
    default_quality_threshold: float


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health_check() -> HealthResponse:
    """
    Returns HTTP 200 if the API process is alive.
    Used by load balancers and container orchestration health checks.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/info", response_model=InfoResponse, summary="Project information")
async def info() -> InfoResponse:
    """
    Returns project metadata and a summary of the current configuration.
    API keys and secrets are never included.
    """
    mem = psutil.virtual_memory()

    # Check component availability (stub — no real connections in Phase-0)
    vector_status = f"configured:{settings.vector_store.provider} @ {settings.vector_store.host}:{settings.vector_store.port} (not connected)"
    graph_status = f"configured:{settings.graph_store.provider} @ {settings.graph_store.uri} (not connected)"
    llm_status = f"configured:{settings.model.default_provider}/{settings.model.default_model_id}"

    return InfoResponse(
        project_name=settings.project_name,
        version=settings.version,
        environment=settings.environment,
        system=SystemInfo(
            python_version=sys.version,
            platform=platform.platform(),
            cpu_count=psutil.cpu_count(logical=True) or 0,
            memory_total_gb=round(mem.total / (1024 ** 3), 2),
            memory_available_gb=round(mem.available / (1024 ** 3), 2),
        ),
        components=ComponentStatus(
            vector_store=vector_status,
            graph_store=graph_status,
            llm_provider=llm_status,
        ),
        default_model=settings.model.default_model_id,
        default_retrieval_strategy=settings.retrieval.default_strategy,
        default_quality_threshold=settings.quality.default_quality_threshold,
    )


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict:
    """
    Readiness probe. In Phase-0 always returns ready.
    Phase-1: will check vector store, graph store, and embedding model.
    """
    return {"status": "ready", "phase": "0-foundation"}
