"""
Engineering Intelligence Hub — Controlled Experiment Manifest (Phase-2 M5)
==========================================================================
Defines the frozen experimental parameters and system specifications for the
M5 comparative benchmark.

Reproducibility Principle:
Every experimental run is bound to a cryptographically hashed manifest.
All variables not under active investigation are FROZEN across all systems.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SystemID(str, Enum):
    """The five experimental systems under comparison in M5."""
    BASELINE_A = "baseline_a"  # LLM only (no RAG, no graph, no gate)
    BASELINE_B = "baseline_b"  # Fixed Hybrid RAG (dense + BM25, no graph, no gate)
    SYSTEM_C   = "system_c"    # Task-Aware Adaptive RAG (M1 + M3, no graph, no gate)
    SYSTEM_D   = "system_d"    # Task-Aware + Knowledge Graph RAG (M1 + M2 + M3, no gate)
    SYSTEM_E   = "system_e"    # Full Proposed System (M1 + M2 + M3 + M4 Quality Gate & Escalation)
    # E + task-aware model routing 1.5B -> 3B -> 7B (plan C1 "model tier selected per
    # task", RQ4). One added capability over E, so delta(E -> E_routed) isolates routing.
    SYSTEM_E_ROUTED = "system_e_routed"


class SystemConfig(BaseModel):
    """Configuration specification for one experimental system."""
    system_id: SystemID
    system_name: str
    description: str
    task_classifier_enabled: bool = False
    retrieval_mode: str = "none"  # "none" | "fixed_hybrid" | "adaptive"
    graph_context_enabled: bool = False
    quality_gate_enabled: bool = False
    escalation_enabled: bool = False
    max_escalations: int = 0
    model_routing_enabled: bool = False
    default_top_k: int = 5
    default_dense_weight: float = 0.70
    default_sparse_weight: float = 0.30

    model_config = ConfigDict(use_enum_values=True)


class FrozenVariables(BaseModel):
    """Parameters frozen across all five systems to ensure a controlled ablation."""
    # Repository Snapshots
    repositories: Dict[str, str] = Field(
        default={
            "pallets/flask": "3.0.3",
            "fastapi/fastapi": "0.111.0",
        },
        description="Pinned immutable repository commit tags",
    )

    # Base LLM Generation Constraints
    llm_provider: str = "ollama"
    llm_model_id: str = "gpt-4o-mini"
    llm_num_ctx: int = 12288
    llm_num_gpu: int = 999
    temperature: float = 0.1
    max_output_tokens: int = 2048
    random_seed: int = 42

    # Embedding Subsystem
    embedding_model_id: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cuda"
    embedding_dimension: int = 384

    # Sustainability & Pricing Parameters
    carbon_intensity_gco2_per_kwh: float = 233.0  # UK national grid 2024 average
    cpu_tdp_watts: float = 45.0
    gpu_tdp_watts: float = 60.0  # RTX 4050 Laptop TGP
    input_cost_per_1m_tokens_usd: float = 0.15
    output_cost_per_1m_tokens_usd: float = 0.60

    # Retrieval and data identity (master prompt Step 1g). Static: file hashes and names.
    retrieval_config_sha256: Optional[str] = None   # configs/retrieval.yaml (strategies, thresholds)
    inference_config_sha256: Optional[str] = None   # configs/inference.yaml (models, ctx, output limit)
    models_config_sha256: Optional[str] = None      # configs/models.yaml (routing ladder)
    vector_collection: Optional[str] = None
    benchmark_tasks_sha256: Optional[str] = None    # benchmark/data/meib_phase1_tasks.json
    benchmark_splits_sha256: Optional[str] = None   # benchmark/data/splits_v1.0.json
    retrieval_labels_sha256: Optional[str] = None   # benchmark/data/retrieval_labels_v1.json
    graph_build_report_sha256: Optional[str] = None  # experiments/results/graph_build/*/graph_build_wave1.json
    # Live: read from the running services when a manifest is frozen with live=True.
    collection_points: Optional[int] = None
    graph_nodes: Optional[int] = None
    graph_edges: Optional[int] = None

    # Experimental Repetitions
    trials_per_task: int = 3

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def from_runtime(cls, live: bool = False) -> "FrozenVariables":
        """The values the pipelines will ACTUALLY use, read from the same sources they read.

        The class defaults above are historical (gpt-4o-mini, UK grid, 2 repos) and
        were never read by any pipeline, so a manifest built from them certified
        settings that did not run. Every manifest is now built from runtime values,
        and `runtime_mismatches()` refuses a manifest that differs from them.
        """
        from core.config import settings
        from core.inference import inference_config
        from sustainability.carbon.estimator import CarbonEstimator

        sus = settings.sustainability
        local = settings.model.default_provider == "ollama"
        ids = static_data_identity()
        if live:
            ids.update(live_data_identity())
        return cls(
            repositories=wave1_repository_pins(),
            llm_provider=settings.model.default_provider,
            llm_model_id=settings.model.default_model_id,
            llm_num_ctx=inference_config().num_ctx,
            llm_num_gpu=inference_config().num_gpu,
            temperature=settings.model.temperature,
            max_output_tokens=settings.model.max_tokens,
            random_seed=inference_config().seed,
            embedding_model_id=settings.vector_store.embedding_model,
            embedding_dimension=settings.vector_store.embedding_dimension,
            carbon_intensity_gco2_per_kwh=CarbonEstimator.from_settings().carbon_intensity,
            cpu_tdp_watts=sus.cpu_tdp_watts,
            gpu_tdp_watts=sus.gpu_tdp_watts,
            input_cost_per_1m_tokens_usd=0.0 if local else sus.default_input_cost_per_1m_tokens,
            output_cost_per_1m_tokens_usd=0.0 if local else sus.default_output_cost_per_1m_tokens,
            **ids,
        )


def wave1_repository_pins() -> Dict[str, str]:
    """repo name -> pinned commit for every wave-1 repository in datasets/registry.yaml."""
    import yaml

    from core.config import PROJECT_ROOT

    registry = yaml.safe_load((PROJECT_ROOT / "datasets" / "registry.yaml").read_text(encoding="utf-8"))
    entries = registry.get("repositories", []) if isinstance(registry, dict) else registry
    return {
        f"{e.get('owner', '')}/{e['name']}".lstrip("/"): e["selected_commit"]
        for e in entries
        if e.get("wave") == 1 and e.get("selected_commit")
    }


LIVE_FIELDS = ("collection_points", "graph_nodes", "graph_edges")


def _sha256_file(path: Path) -> Optional[str]:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def graph_build_report() -> Optional[Path]:
    """The wave-1 graph build report (exactly one expected)."""
    from core.config import PROJECT_ROOT

    found = sorted((PROJECT_ROOT / "experiments" / "results" / "graph_build").glob("*/graph_build_wave1.json"))
    if len(found) > 1:
        raise RuntimeError(f"several wave-1 graph build reports: {found}")
    return found[0] if found else None


def static_data_identity() -> Dict[str, Any]:
    """Hashes of the configs and data files a run depends on; no service is contacted."""
    from core.config import PROJECT_ROOT, settings

    data = PROJECT_ROOT / "benchmark" / "data"
    report = graph_build_report()
    return {
        "retrieval_config_sha256": _sha256_file(PROJECT_ROOT / "configs" / "retrieval.yaml"),
        "inference_config_sha256": _sha256_file(PROJECT_ROOT / "configs" / "inference.yaml"),
        "models_config_sha256": _sha256_file(PROJECT_ROOT / "configs" / "models.yaml"),
        "vector_collection": settings.vector_store.collection_name,
        "benchmark_tasks_sha256": _sha256_file(data / "meib_phase1_tasks.json"),
        "benchmark_splits_sha256": _sha256_file(data / "splits_v1.0.json"),
        "retrieval_labels_sha256": _sha256_file(data / "retrieval_labels_v1.json"),
        "graph_build_report_sha256": _sha256_file(report) if report else None,
    }


def live_data_identity() -> Dict[str, Any]:
    """Point count of the vector collection and node/edge counts of the live graph."""
    from core.config import settings
    from knowledge.graph.neo4j import Neo4jGraphStore
    from knowledge.vector.qdrant import QdrantVectorStore

    vs = QdrantVectorStore()
    gs = settings.graph_store
    graph = Neo4jGraphStore(uri=gs.uri, username=gs.username, password=gs.password)
    if not graph.is_available():
        raise RuntimeError("Neo4j is not reachable; the graph identity cannot be checked")
    return {"collection_points": vs.count(settings.vector_store.collection_name),
            "graph_nodes": graph.count_nodes(), "graph_edges": graph.count_edges()}


def runtime_mismatches(manifest: "ExperimentManifest", live: bool = False) -> List[Dict[str, Any]]:
    """Fields where the manifest differs from what the pipelines would actually run with.

    With live=True the running Qdrant collection and Neo4j graph are checked too, and the live
    graph must equal the graph build report (a graph changed after its build, even by 2 test
    nodes, is not the graph the report describes).
    """
    want = FrozenVariables.from_runtime(live=live).model_dump()
    have = manifest.frozen_variables.model_dump()
    skip = {"trials_per_task"} | (set() if live else set(LIVE_FIELDS))
    out = [{"field": k, "manifest": have.get(k), "runtime": v}
           for k, v in want.items() if k not in skip and have.get(k) != v]
    if live:
        report = graph_build_report()
        if report is None:
            out.append({"field": "graph_build_report", "manifest": None, "runtime": "missing"})
        else:
            rb = json.loads(report.read_text(encoding="utf-8"))["results"]["read_back"]
            if (rb["nodes"], rb["edges"]) != (want["graph_nodes"], want["graph_edges"]):
                out.append({"field": "graph_vs_build_report",
                            "manifest": {"nodes": rb["nodes"], "edges": rb["edges"]},
                            "runtime": {"nodes": want["graph_nodes"], "edges": want["graph_edges"]}})
    return out


class ExperimentManifest(BaseModel):
    """
    Self-describing experiment manifest for Phase-2 M5.
    """
    manifest_version: str = "1.0"
    # v1.1 (2026-10-05): 16 dev/val tasks corrected against the pinned source, approved by
    # Avaneesh (4 answers/questions, 12 cited-evidence locations); split assignment unchanged.
    benchmark_version: str = "v1.1-phase1-60"
    created_at: str = "2026-08-20T00:00:00Z"
    frozen_variables: FrozenVariables = Field(default_factory=FrozenVariables)
    systems: Dict[str, SystemConfig] = Field(default_factory=dict)
    hardware_specification: Dict[str, str] = Field(
        default={
            "cpu": "Intel Core x86_64",
            "gpu": "NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM)",
            "cuda_version": "12.4",
            "os": "Windows 11",
        }
    )

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def create_default(cls, live: bool = False) -> "ExperimentManifest":
        """Factory: build default M5 manifest with the 5 standard systems."""
        systems = {
            SystemID.BASELINE_A.value: SystemConfig(
                system_id=SystemID.BASELINE_A,
                system_name="Baseline A: LLM-Only",
                description="Zero-retrieval baseline. Prompt directly sent to LLM without external evidence.",
                task_classifier_enabled=False,
                retrieval_mode="none",
                graph_context_enabled=False,
                quality_gate_enabled=False,
                escalation_enabled=False,
                max_escalations=0,
            ),
            SystemID.BASELINE_B.value: SystemConfig(
                system_id=SystemID.BASELINE_B,
                system_name="Baseline B: Fixed Hybrid RAG",
                description="Phase-1 Fixed Hybrid RAG. Fixed dense (0.7) + BM25 (0.3) retrieval with top_k=5.",
                task_classifier_enabled=False,
                retrieval_mode="fixed_hybrid",
                graph_context_enabled=False,
                quality_gate_enabled=False,
                escalation_enabled=False,
                max_escalations=0,
                default_top_k=5,
                default_dense_weight=0.70,
                default_sparse_weight=0.30,
            ),
            SystemID.SYSTEM_C.value: SystemConfig(
                system_id=SystemID.SYSTEM_C,
                system_name="System C: Task-Aware Adaptive RAG",
                description="M1 Task Intelligence dynamically selects M3 retrieval policy. No graph or quality gate.",
                task_classifier_enabled=True,
                retrieval_mode="adaptive",
                graph_context_enabled=False,
                quality_gate_enabled=False,
                escalation_enabled=False,
                max_escalations=0,
            ),
            SystemID.SYSTEM_D.value: SystemConfig(
                system_id=SystemID.SYSTEM_D,
                system_name="System D: Task-Aware + Knowledge Graph RAG",
                description="M1 Task Intelligence + M3 Adaptive Retrieval + M2 AST Knowledge Graph. No quality gate.",
                task_classifier_enabled=True,
                retrieval_mode="adaptive",
                graph_context_enabled=True,
                quality_gate_enabled=False,
                escalation_enabled=False,
                max_escalations=0,
            ),
            SystemID.SYSTEM_E.value: SystemConfig(
                system_id=SystemID.SYSTEM_E,
                system_name="System E: Full Proposed System",
                description="M1 Task Intelligence + M2 Graph + M3 Adaptive + M4 Quality Gate & Bounded Escalation.",
                task_classifier_enabled=True,
                retrieval_mode="adaptive",
                graph_context_enabled=True,
                quality_gate_enabled=True,
                escalation_enabled=True,
                max_escalations=3,
            ),
        }
        systems[SystemID.SYSTEM_E_ROUTED.value] = systems[SystemID.SYSTEM_E.value].model_copy(update={
            "system_id": SystemID.SYSTEM_E_ROUTED,
            "system_name": "System E + model routing (RQ4)",
            "description": "System E with task-aware model routing over the local ladder "
                           "(small 1.5B, medium 3B, large 7B; escalation climbs the ladder).",
            "model_routing_enabled": True,
        })
        return cls(systems=systems, frozen_variables=FrozenVariables.from_runtime(live=live))

    def compute_hash(self) -> str:
        """Compute SHA-256 fingerprint of the manifest configuration."""
        serialized = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
