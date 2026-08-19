# CHANGELOG

All notable changes to Engineering Intelligence Hub are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Phase-2 Quality-Aware Verification (`M4`)**:
  - `verification/config.py`: `VerificationConfig` Pydantic model for configurable signal weights and escalation parameters.
  - `verification/evaluators.py`: 4 deterministic evaluators (`CitationGroundingEvaluator`, `EvidenceCoverageEvaluator`, `QueryRelevanceEvaluator`, `EvidenceConsistencyEvaluator`).
  - `verification/escalation.py`: `EscalationPolicy` implementing bounded progressive strategy escalation (top-k expansion -> graph depth -> reranking).
  - `verification/gate.py`: `QualityGate.default_gate()` factory and task-specific threshold resolution.
  - `generation/quality_rag.py`: `QualityAwareRAGPipeline` integrating generation, quality gate, bounded escalation, and fallback to `INSUFFICIENT EVIDENCE`.
  - `apps/api/routers/adaptive.py`: Added `POST /adaptive/query` and `POST /adaptive/verify` endpoints.
  - `docs/quality_verification.md`: Complete architecture and telemetry documentation.
  - `tests/test_verification/test_m4_quality_gate.py`: 21 comprehensive unit & pipeline tests (125 total passing tests).
- **Phase-2 Adaptive Retrieval Subsystem (`M3`)**:
  - `retrieval/policy.py`: `AdaptiveRetrievalPolicy` mapping 21 SDLC task types to retrieval strategies with criticality escalation.
  - `retrieval/graph_augmented.py`: `GraphAugmentedRetriever` with bounded graph neighborhood context injection.
  - `retrieval/adaptive.py`: `AdaptiveRetrievalPipeline` supporting `BASELINE_B`, `SYSTEM_C`, and `SYSTEM_D` experiment modes.
  - `configs/retrieval.yaml`: Added `hybrid_bm25`, `incident_sparse`, and `incident_graph` strategies.
  - `tests/test_retrieval/test_m3_adaptive.py`: 25 adaptive retrieval tests.
- **Phase-2 Engineering Knowledge Graph Foundation (`M2`)**:
  - `knowledge/graph/neo4j.py`: `Neo4jGraphStore` implementation with Bolt protocol connection, index constraints, and parameterized Cypher execution.
  - `knowledge/graph/in_memory.py`: `InMemoryGraphStore` implementation for fast, reliable unit tests without database dependencies.
  - `knowledge/graph/extractor.py`: `ASTGraphExtractor` extracting code entities (Module, Class, Function, Method, Test) and relationships (CONTAINS, IMPORTS, DEPENDS_ON, CALLS, TESTED_BY) with strict line-level provenance.
  - `knowledge/graph/builder.py`: `EngineeringGraphBuilder` building and persisting repository-level knowledge graphs from source files, commits, pull requests, issues, and ADRs with deterministic idempotency.
  - `knowledge/graph/queries.py`: Graph traversal and query helpers (`get_entity`, `get_neighborhood`, `find_dependencies`, `find_related_files`, `find_issue_commits`, `find_modified_files`, `get_subgraph`).
  - `apps/api/routers/graph.py`: REST API endpoints for `/graph/health`, `/graph/entity/{id}`, and `/graph/neighbors/{id}`.
  - `docs/knowledge_graph.md`: Comprehensive graph schema, provenance strategy, and reference documentation.
  - Unit and API tests in `tests/test_knowledge/` and `tests/test_api/test_graph_endpoints.py` (all 104 tests green).
- **Phase-2 Task Intelligence Subsystem (`M1`)**:
  - `intelligence/base.py`: Abstract `BaseTaskClassifier` interface.
  - `intelligence/complexity.py`: `HeuristicComplexityAnalyzer` evaluating query length, architectural cues, deep reasoning cues, and multi-step patterns.
  - `intelligence/criticality.py`: `HeuristicCriticalityAnalyzer` evaluating operational criticality, security sensitivity, and quality thresholds.
  - `intelligence/classifier.py`: `RuleBasedTaskClassifier` mapping user prompts and hints to `SDLCStage`, `TaskType`, `ComplexityLevel`, and `CriticalityLevel`.
  - `intelligence/__init__.py`: Exported package module.
  - `tests/test_intelligence/`: Unit tests for task classifier, complexity, and criticality analyzers (8 tests passing).
  - `docs/task_intelligence.md`, `docs/phase2_architecture.md`: Comprehensive design and reference documentation.

---

## [0.2.0] - 2026-08-19 — Phase-1 Baseline RAG

### Added
- **Repository Ingestion Engine**:
  - `ingestion/loaders/file_loader.py` — Directory walker with exclusions and artifact classification.
  - `ingestion/loaders/github_loader.py` — Cloner with pinned commit/tag checkouts, commit history, issues, PRs.
  - `ingestion/processors/chunker.py` — Python AST `CodeAwareChunker` and heading-based `DocAwareChunker`.
  - `ingestion/processors/normalizer.py` — BOM/line-ending normalization, SHA-256 deduplication.
  - `ingestion/registry.py` — Registry parser for repository specifications.
  - `datasets/registry.yaml` — Pinned repository specifications for `pallets/flask` (3.0.3) and `fastapi/fastapi` (0.111.0).
- **GPU Embeddings & Vector Store**:
  - `knowledge/vector/embeddings.py` — `BGEEmbeddingModel` on `BAAI/bge-small-en-v1.5` with CUDA / RTX 4050 GPU acceleration and batching.
  - `knowledge/vector/qdrant.py` — Concrete `QdrantVectorStore` implementation with live Docker integration.
  - `docker-compose.yml` — Upgraded Qdrant to `qdrant/qdrant:v1.13.2`.
- **Hybrid Retrieval Subsystem**:
  - `retrieval/dense.py` — Qdrant-backed semantic vector retriever.
  - `retrieval/bm25.py` — BM25Plus sparse retriever with software-engineering code tokenization.
  - `retrieval/hybrid.py` — Weighted score fusion with score normalization and metadata filtering.
- **LLM Provider & Baseline RAG Pipeline**:
  - `generation/providers/openai.py` — `OpenAIProvider` and offline `MockLLMProvider`.
  - `generation/rag.py` — `BaselineRAGPipeline` with grounded reasoning, source citation, and refusal handling.
- **Benchmark Suite**:
  - `benchmark/data/meib_phase1_tasks.json` — 60 verified benchmark tasks across 6 SDLC stages.
  - `benchmark/validator.py` — Quality validator and `CANDIDATE` -> `APPROVED` promotion manager.
  - `benchmark/dataset.py` — Dataset filtering, loading, and analytical distributions.
- **Evaluation Framework & Baselines**:
  - `experiments/baselines/baseline_a.py` — `BaselineARunner` (LLM-only baseline).
  - `experiments/baselines/baseline_b.py` — `BaselineBRunner` (Fixed RAG baseline).
  - `evaluation/scorers/correctness.py`, `groundedness.py`, `relevance.py` — Specialized evaluators.
  - `evaluation/suite.py` — `BaselineEvaluatorSuite`.
- **REST API Endpoints**:
  - `apps/api/routers/ingest.py` — `POST /ingest/repository`, `POST /ingest/file`.
  - `apps/api/routers/retrieval.py` — `POST /retrieve`.
  - `apps/api/routers/query.py` — `POST /query`.
- **Documentation**:
  - `docs/phase1_architecture.md`, `docs/ingestion.md`, `docs/retrieval.md`, `docs/benchmark.md`, `docs/evaluation.md`, `docs/sustainability_measurement.md`.

---

## [0.1.0] - 2026-08-19 — Phase-0 Foundation

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
