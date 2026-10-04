"""
Engineering Intelligence Hub — Configuration Management
========================================================
Loads configuration from:
  1. Environment variables (highest priority — good for secrets)
  2. .env file (local development)
  3. configs/default.yaml (project defaults)

All settings are typed via Pydantic BaseSettings.

Usage
-----
    from core.config import settings
    print(settings.api_host)
    print(settings.default_model_id)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the project (two levels above this file: core/ → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Every settings group reads the project .env file. Nested groups are built via
# default_factory, so they do NOT inherit env_file from the top-level Settings:
# without passing it to each group, every EIH_<GROUP>_* line in .env was silently
# ignored (only real OS environment variables were read).
ENV_FILE = str(PROJECT_ROOT / ".env")


def _load_yaml_defaults() -> Dict:
    """Load YAML defaults from configs/default.yaml, silently ignoring missing file."""
    yaml_path = PROJECT_ROOT / "configs" / "default.yaml"
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class APISettings(BaseSettings):
    """FastAPI application settings."""

    host: str = Field(default="0.0.0.0", description="API bind host")
    port: int = Field(default=8000, description="API bind port")
    reload: bool = Field(default=False, description="Hot-reload for development")
    workers: int = Field(default=1, description="Number of Uvicorn workers")
    cors_origins: List[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_API_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class ModelSettings(BaseSettings):
    """Default model routing settings."""

    # Local-only inference (RD-013): every system runs on the Ollama model ladder.
    # The fixed model for Systems A-E is the 7B (decision 2026-10-05); model
    # routing (routing/tier_router.py) is an added system compared against it.
    default_provider: str = Field(
        default="ollama", description="Default LLM provider ID: ollama | openai | mock"
    )
    default_model_id: str = Field(
        default="qwen2.5-coder:7b", description="Fixed model for non-routed systems"
    )
    fallback_model_id: str = Field(
        default="qwen2.5-coder:3b", description="Fallback model for failed routing"
    )
    max_tokens: int = Field(default=2048, description="Maximum output tokens")
    temperature: float = Field(
        default=0.0, description="Sampling temperature (0 = deterministic with a fixed seed)"
    )
    request_timeout_seconds: int = Field(
        default=120, description="Provider request timeout"
    )
    max_retries: int = Field(default=3, description="Maximum retries on transient errors")

    model_config = SettingsConfigDict(
        env_prefix="EIH_MODEL_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class RetrievalSettings(BaseSettings):
    """Default retrieval configuration."""

    default_strategy: str = Field(
        default="hybrid", description="Default retrieval strategy name"
    )
    default_top_k: int = Field(default=5, description="Default number of chunks to retrieve")
    similarity_threshold: float = Field(
        default=0.7, description="Minimum cosine similarity score"
    )
    enable_reranking: bool = Field(default=False, description="Enable reranking by default")
    max_context_chunks: int = Field(
        default=10, description="Maximum chunks sent to generation"
    )
    reranker_model_id: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder checkpoint used by the reranking stage",
    )
    strict_reranking: bool = Field(
        default=False,
        description=(
            "If True, a strategy requesting reranking that cannot run raises "
            "RetrievalError instead of degrading to unreranked output. Enable for "
            "final experiment runs so a skipped reranker cannot silently "
            "invalidate results."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_RETRIEVAL_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class QualitySettings(BaseSettings):
    """Quality gate configuration."""

    default_quality_threshold: float = Field(
        default=0.75,
        description="Default minimum acceptable quality score (0.0–1.0)",
    )
    max_escalation_attempts: int = Field(
        default=3,
        description="Maximum escalation rounds before refusing (3 = reranking rung reachable)",
    )
    enable_code_compilation_check: bool = Field(
        default=False, description="Run compilation checks on generated code"
    )
    enable_test_execution: bool = Field(
        default=False, description="Execute generated tests as quality signal"
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_QUALITY_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class SustainabilitySettings(BaseSettings):
    """Sustainability measurement configuration."""

    # Region whose grid carbon intensity applies to THIS experiment run.
    # Must name a key in sustainability.carbon.estimator.CARBON_INTENSITIES_GCO2_PER_KWH,
    # or "custom" to use carbon_intensity_gco2_per_kwh directly.
    #
    # IMPORTANT (research validity): carbon intensity is location-dependent and
    # varies by more than an order of magnitude between grids (France ~56,
    # UK ~233, India ~713 gCO2e/kWh). Reporting CO2e without stating the region
    # is not a defensible result. Set this to where inference ACTUALLY ran, and
    # disclose the value in the report.
    carbon_region: str = Field(
        default="custom",
        description="Grid region key for CO2e, or 'custom' to use the explicit intensity below",
    )
    carbon_intensity_gco2_per_kwh: float = Field(
        default=713.0,
        description=(
            "Grid carbon intensity in gCO2e/kWh used when carbon_region='custom'. "
            "Defaults to the India national grid average (2023), matching the "
            "project's actual execution location."
        ),
    )
    # TDP proxy for energy estimation when GPU power is unavailable.
    cpu_tdp_watts: float = Field(
        default=45.0,
        description="CPU TDP in watts — used as proxy when psutil power unavailable",
    )
    gpu_tdp_watts: float = Field(
        default=60.0,
        description="GPU TDP in watts — RTX 4050 Laptop GPU TGP",
    )
    enable_gpu_measurement: bool = Field(
        default=True, description="Attempt GPU utilisation measurement via pynvml"
    )
    # Monetary cost defaults (USD per 1M tokens) — override per model.
    default_input_cost_per_1m_tokens: float = Field(
        default=0.15, description="Default input token cost USD/1M"
    )
    default_output_cost_per_1m_tokens: float = Field(
        default=0.60, description="Default output token cost USD/1M"
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_SUSTAINABILITY_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class ExperimentSettings(BaseSettings):
    """Experiment tracking configuration."""

    results_dir: Path = Field(
        default=PROJECT_ROOT / "experiments" / "results",
        description="Root directory for experiment result storage",
    )
    log_every_call: bool = Field(
        default=True, description="Log every LLM call as an experiment event"
    )
    experiment_id_prefix: str = Field(
        default="eih", description="Prefix for auto-generated experiment IDs"
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_EXPERIMENT_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class LLMProviderSecrets(BaseSettings):
    """
    LLM provider API keys and endpoints.
    NEVER commit these — load from environment or .env file only.
    """

    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY")
    together_api_key: Optional[str] = Field(default=None, validation_alias="TOGETHER_API_KEY")
    huggingface_token: Optional[str] = Field(default=None, validation_alias="HF_TOKEN")
    # For locally-hosted models (Ollama, vLLM, etc.)
    local_model_base_url: Optional[str] = Field(
        default=None, validation_alias="EIH_LOCAL_MODEL_BASE_URL"
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class VectorStoreSettings(BaseSettings):
    """Vector store connection settings."""

    provider: str = Field(default="qdrant", description="Vector store provider")
    host: str = Field(default="localhost", description="Vector store host")
    port: int = Field(default=6333, description="Vector store port")
    collection_name: str = Field(
        default="eih_knowledge", description="Default collection name"
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Sentence-transformer model for embeddings",
    )
    embedding_dimension: int = Field(
        default=384, description="Embedding vector dimension"
    )

    model_config = SettingsConfigDict(
        env_prefix="EIH_VECTOR_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class GraphStoreSettings(BaseSettings):
    """Graph database connection settings."""

    provider: str = Field(default="neo4j", description="Graph store provider")
    uri: str = Field(default="bolt://localhost:7687", description="Neo4j bolt URI")
    username: str = Field(default="neo4j", description="Graph store username")
    password: Optional[str] = Field(default=None, validation_alias="EIH_GRAPH_PASSWORD")

    model_config = SettingsConfigDict(
        env_prefix="EIH_GRAPH_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


class Settings(BaseSettings):
    """
    Top-level aggregated settings for Engineering Intelligence Hub.

    Individual sub-settings are instantiated here for convenient access:
        settings.api.port
        settings.model.default_provider
        settings.retrieval.default_top_k
        settings.quality.default_quality_threshold
        settings.sustainability.carbon_intensity_gco2_per_kwh
        settings.experiment.results_dir
        settings.secrets.openai_api_key  # ← None if not set
        settings.vector_store.provider
        settings.graph_store.provider
    """

    # --- Environment flag ---
    environment: str = Field(
        default="development",
        description="Runtime environment: development | testing | production",
    )
    machine_id: str = Field(
        default="unknown",
        description=(
            "Which development machine produced a result (laptop-a | laptop-b), "
            "from EIH_MACHINE_ID. Recorded in every result file's provenance."
        ),
    )
    log_level: str = Field(default="INFO", description="Root log level")
    json_logs: bool = Field(default=False, description="Enable JSON-serialised logs")
    project_name: str = Field(
        default="Engineering Intelligence Hub",
        description="Human-readable project name",
    )
    version: str = Field(default="0.1.0", description="Application version")

    # Sub-settings (instantiated with their own env-prefix loaders)
    api: APISettings = Field(default_factory=APISettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    quality: QualitySettings = Field(default_factory=QualitySettings)
    sustainability: SustainabilitySettings = Field(
        default_factory=SustainabilitySettings
    )
    experiment: ExperimentSettings = Field(default_factory=ExperimentSettings)
    secrets: LLMProviderSecrets = Field(default_factory=LLMProviderSecrets)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    graph_store: GraphStoreSettings = Field(default_factory=GraphStoreSettings)

    model_config = SettingsConfigDict(
        env_prefix="EIH_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ---------------------------------------------------------------------------
# Module-level singleton — import and use anywhere in the codebase.
# ---------------------------------------------------------------------------
settings = Settings()
