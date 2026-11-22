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


@router.get("/ready", summary="Readiness probe (real checks)")
def ready() -> dict:
    """Ready only when every required service answers: Qdrant (research collection with points),
    Neo4j, Ollama with the configured model. Each check reports its own state; nothing is assumed."""
    checks = system_status()["services"]
    required = ("qdrant", "neo4j", "ollama")
    ok = all(checks[k]["ok"] for k in required)
    return {"status": "ready" if ok else "not_ready", "checks": {k: checks[k] for k in required}}


def _pinned_digests() -> dict:
    import yaml

    from core.config import PROJECT_ROOT
    models = yaml.safe_load((PROJECT_ROOT / "configs" / "models.yaml").read_text(encoding="utf-8"))["models"]
    return {m["model_id"]: (m.get("extra") or {}).get("digest") for m in models}


@router.get("/status", summary="Service status for the UI")
def system_status() -> dict:
    """Qdrant, Neo4j, Ollama (+ pinned-digest check), GPU, OKF; measured live on every call."""
    import httpx

    out: dict = {"machine_id": settings.machine_id, "checked_at": datetime.now(timezone.utc).isoformat()}
    s: dict = {}
    # Qdrant
    try:
        from knowledge.vector.qdrant import QdrantVectorStore
        vs = QdrantVectorStore()
        vs.connect()
        coll = settings.vector_store.collection_name
        n = vs.count(coll) if vs.collection_exists(coll) else 0
        okf_n = vs.count(settings.okf.collection_name) if vs.collection_exists(settings.okf.collection_name) else 0
        s["qdrant"] = {"ok": n > 0, "collection": coll, "points": n, "okf_collection": settings.okf.collection_name,
                       "okf_points": okf_n}
    except Exception as exc:  # noqa: BLE001
        s["qdrant"] = {"ok": False, "error": str(exc)[:200]}
    # Neo4j
    try:
        from knowledge.graph.neo4j import Neo4jGraphStore
        g = Neo4jGraphStore()
        if g.is_available():
            okf = g.query("MATCH (c:OKFConcept) RETURN count(c) AS n")[0]["n"]
            s["neo4j"] = {"ok": True, "entity_nodes": g.count_nodes(), "entity_edges": g.count_edges(),
                          "okf_concepts": okf}
        else:
            s["neo4j"] = {"ok": False, "error": "not reachable"}
    except Exception as exc:  # noqa: BLE001
        s["neo4j"] = {"ok": False, "error": str(exc)[:200]}
    # Ollama
    base = settings.secrets.local_model_base_url or "http://localhost:11434"
    try:
        tags = httpx.get(f"{base.rstrip('/')}/api/tags", timeout=3).json().get("models", [])
        version = httpx.get(f"{base.rstrip('/')}/api/version", timeout=3).json().get("version")
        pinned = _pinned_digests()
        models = []
        for mid, digest in pinned.items():
            got = next((m.get("digest") for m in tags if m.get("name") == mid or m.get("model") == mid), None)
            models.append({"model_id": mid, "pulled": got is not None, "digest": got,
                           "digest_matches_pin": (got == digest) if got and digest else None})
        default = settings.model.default_model_id
        s["ollama"] = {"ok": any(m["model_id"] == default and m["pulled"] for m in models), "version": version,
                       "default_model": default, "models": models}
    except Exception as exc:  # noqa: BLE001
        s["ollama"] = {"ok": False, "error": f"not reachable at {base}: {str(exc)[:120]}"}
    # GPU
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        s["gpu"] = {"ok": True, "name": pynvml.nvmlDeviceGetName(h), "driver": pynvml.nvmlSystemGetDriverVersion(),
                    "vram_used_mib": mem.used // 2**20, "vram_total_mib": mem.total // 2**20,
                    "temperature_c": pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)}
        pynvml.nvmlShutdown()
    except Exception as exc:  # noqa: BLE001
        s["gpu"] = {"ok": False, "error": str(exc)[:200]}
    # OKF
    try:
        from apps.api import services
        names = services.bundle_names()
        s["okf"] = {"ok": bool(names), "bundles": names, "default_bundle": settings.okf.default_bundle}
    except Exception as exc:  # noqa: BLE001
        s["okf"] = {"ok": False, "error": str(exc)[:200]}
    out["services"] = s
    return out
