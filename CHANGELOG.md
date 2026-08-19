# CHANGELOG

All notable changes to Engineering Intelligence Hub are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed
- Migrated primary virtual environment to Python 3.11.9 (`.venv311/`), preserving `.venv/` (Python 3.8.10) for reference.
- Upgraded schema configurations from legacy `class Config` to modern Pydantic v2 `model_config = ConfigDict(use_enum_values=True)` across all schema and config modules.
- Enhanced `.gitignore` with strict exclusion rules for model caches (`.cache/`, `model_cache/`, `hf_cache/`), raw experimental datasets, local databases, and temporary artifacts.

### Added
- `docs/environment.md` — Full hardware, CUDA, Python 3.11, Docker, and environment readiness specification.


### Added

#### Core
- `core/config.py` — Pydantic v2 Settings with nested sub-configs (API, model, retrieval, quality, sustainability, experiment, secrets, vector store, graph store)
- `core/logging.py` — Loguru-based structured logging with JSON and rotating file sinks
- `core/exceptions.py` — Full exception hierarchy: `EIHException` → 15 typed exceptions

#### Knowledge Schemas
- `knowledge/schemas/artifacts.py` — `SourceFile`, `Commit`, `Issue`, `PullRequest`, `TestCase`, `IncidentReport`, `ArchitectureDecision`, `KnowledgeChunk`
- `knowledge/schemas/tasks.py` — `EngTaskRequest`, `EngTaskResponse`, `TaskClassification`, `SDLCStage`, `TaskType`, `ComplexityLevel`, `CriticalityLevel`, `SecuritySensitivity`
- `knowledge/schemas/benchmark.py` — `BenchmarkTask`, `SourceEvidence`, `QualitySignalRequirements`, `BenchmarkTaskStatus`

#### Abstract Interfaces
- `ingestion/base.py` — `BaseIngestionSource`, `BaseChunker` ABCs
- `knowledge/vector/base.py` — `BaseVectorStore` ABC (connect, upsert, search, keyword_search, delete, count)
- `knowledge/graph/base.py` — `BaseGraphStore` ABC with `NodeLabel`, `RelationshipType`, `GraphNode`, `GraphEdge`
- `retrieval/base.py` — `BaseRetriever` ABC
- `retrieval/strategies.py` — `RetrievalStrategyConfig` Pydantic model
- `retrieval/router.py` — `RetrievalRouter` (config-driven, task-type→strategy mapping)
- `routing/base.py` — `BaseModelRouter` ABC
- `routing/registry.py` — `ModelCapabilityProfile`, `ModelRegistry` with YAML loading
- `routing/policies.py` — `RoutingPolicy` with α,β,γ,δ,ε objective weights
- `generation/base.py` — `BaseLLMProvider`, `GenerationRequest`, `GenerationResponse`
- `verification/base.py` — `BaseQualityEvaluator` ABC
- `verification/signals.py` — `QualitySignal`, `QualityReport` with weighted aggregation
- `verification/gate.py` — `QualityGate` with PASS/ESCALATE/FAIL logic
- `sustainability/base.py` — `BaseResourceMeasurement` ABC with system boundary documentation
- `sustainability/energy/estimator.py` — `EnergyEstimator` (TDP proxy + optional NVML)
- `sustainability/cost/estimator.py` — `CostEstimator` with reference pricing table
- `sustainability/carbon/estimator.py` — `CarbonEstimator` with regional intensities
- `evaluation/base.py` — `BaseEvaluator` ABC
- `evaluation/metrics.py` — `QualityMetrics`, `EfficiencyMetrics`, `EngineeringOutcomeMetrics`, `ExperimentResult`
- `experiments/config.py` — `ExperimentConfig` schema with full reproducibility fields
- `experiments/logger.py` — JSONL `ExperimentLogger` with typed event methods
- `experiments/runner.py` — `BaseExperimentRunner` ABC

#### API
- `apps/api/main.py` — FastAPI application skeleton with lifespan and CORS
- `apps/api/routers/health.py` — `/health`, `/info`, `/ready` endpoints

#### Configuration
- `configs/default.yaml` — System-wide defaults
- `configs/models.yaml` — 7 model profiles (OpenAI, Anthropic, Google, Local)
- `configs/retrieval.yaml` — 7 named retrieval strategies
- `experiments/baselines/baseline_a.yaml` — Baseline A (LLM-only) config
- `.env.example` — Environment variable template

#### Documentation
- `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `RESEARCH_NOTES.md`, `EXPERIMENT_PLAN.md`, `DATASET_PLAN.md`

#### Tests
- 50+ test cases across schemas, retrieval, verification, sustainability, and experiment logger
- All tests pass on Python 3.8 with no external service dependencies
