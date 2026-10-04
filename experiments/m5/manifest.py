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
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


class SystemID(str, Enum):
    """The five experimental systems under comparison in M5."""
    BASELINE_A = "baseline_a"  # LLM only (no RAG, no graph, no gate)
    BASELINE_B = "baseline_b"  # Fixed Hybrid RAG (dense + BM25, no graph, no gate)
    SYSTEM_C   = "system_c"    # Task-Aware Adaptive RAG (M1 + M3, no graph, no gate)
    SYSTEM_D   = "system_d"    # Task-Aware + Knowledge Graph RAG (M1 + M2 + M3, no gate)
    SYSTEM_E   = "system_e"    # Full Proposed System (M1 + M2 + M3 + M4 Quality Gate & Escalation)


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
    llm_model_id: str = "gpt-4o-mini"
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

    # Experimental Repetitions
    trials_per_task: int = 3

    model_config = ConfigDict(use_enum_values=True)


class ExperimentManifest(BaseModel):
    """
    Self-describing experiment manifest for Phase-2 M5.
    """
    manifest_version: str = "1.0"
    benchmark_version: str = "v1.0-phase1-60"
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
    def create_default(cls) -> "ExperimentManifest":
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
        return cls(systems=systems)

    def compute_hash(self) -> str:
        """Compute SHA-256 fingerprint of the manifest configuration."""
        serialized = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
