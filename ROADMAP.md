# ROADMAP

Engineering Intelligence Hub — Six-Month Development Roadmap

---

## Milestone 1 — Research Presentation (25 August 2026)

**Deliverable:** Research PPT covering:
- Title and problem statement
- Literature review (RAG, green AI, software engineering agents, adaptive retrieval, model routing)
- Research gap and novelty statement (conservative, evidence-based)
- Proposed system architecture
- Expected output types and evaluation methodology

**Code status:** Phase-0 foundation complete.

---

## Milestone 2 — Baseline System + Initial Benchmark (15 September 2026)

**Deliverable:** Research paper draft + baseline system working + initial benchmark + evaluation framework.

### Phase-1 Goals (Completed Ahead of Schedule)

- [x] **Ingestion pipeline** — GitHub loader for commits, issues, PRs; file loaders for Python AST, Markdown, YAML
- [x] **Embedding** — BAAI/bge-small-en-v1.5 (local CUDA RTX 4050 GPU) + telemetry benchmarking
- [x] **Vector store** — Qdrant integration (`QdrantVectorStore` implementing `BaseVectorStore`, v1.13.2)
- [x] **Hybrid retrieval** — Dense + BM25Plus fusion; concrete `HybridRetriever` with weighted fusion
- [x] **LLM providers** — `OpenAIProvider` and `MockLLMProvider`
- [x] **Baselines A and B** — `BaselineARunner` (LLM-only) and `BaselineBRunner` (Fixed RAG)
- [x] **Initial benchmark** — 60 verified development tasks across 6 SDLC stages in 2 pinned repositories (`pallets/flask`, `fastapi/fastapi`)
- [x] **Evaluation framework** — Correctness + groundedness + relevance evaluators and `BaselineEvaluatorSuite`
- [x] **Sustainability instrumentation** — All calls instrumented with energy/cost/CO₂ estimates and NVML GPU telemetry
- [x] **Docker Compose** — Qdrant + Neo4j services configured and verified

---

## Milestone 3 — Major Implementation + Experiments (25 October 2026)

### Phase-2 Goals (In Progress)

- [x] **Task Intelligence (M1)** — `RuleBasedTaskClassifier`, `HeuristicComplexityAnalyzer`, and `HeuristicCriticalityAnalyzer`
- [x] **Knowledge Graph Foundation (M2)** — Concrete `Neo4jGraphStore`, `InMemoryGraphStore`, `ASTGraphExtractor`, and `EngineeringGraphBuilder`
- [x] **Adaptive Retrieval (M3)** — Dynamic retrieval strategy selection driven by `TaskClassification`, `AdaptiveRetrievalPolicy`, `GraphAugmentedRetriever`, `AdaptiveRetrievalPipeline`
- [x] **Quality-Aware Verification (M4)** — Four-signal quality gate driven by task criticality with bounded retrieval escalation and `QualityAwareRAGPipeline`
- [ ] **Controlled Evaluation (M5)** — Comparative evaluation of Baselines A, B, and Systems C, D, E
- [ ] **Baselines C, D, E, F** — All named experimental configurations running
- [ ] **Ablation studies** — Disable retrieval, disable routing, disable quality gate, vary thresholds
- [ ] **Pareto analysis** — Quality vs energy/cost/latency Pareto frontier plots
- [ ] **Benchmark expanded** — ~400 tasks across 4–5 repositories, human-reviewed subset
- [ ] **Updated research** — Incorporate empirical results

### Phase-3 Goals

- [ ] **Graph store** — Neo4j integration (`Neo4jGraphStore`)
- [ ] **Graph-augmented retrieval** — Architecture Q&A, dependency analysis
- [ ] **Knowledge graph population** — Repository entity extraction
- [ ] **Code evaluator** — Compilation + test execution checks

---

## Milestone 4 — Final Submission (15 November 2026)

- [ ] Final paper with complete experiments and results
- [ ] Final code freeze with reproducibility documentation
- [ ] Final benchmark (hidden test set frozen)
- [ ] Final Pareto analysis and ablation results
- [ ] Plagiarism check < 10%
- [ ] Reproducibility documentation (hardware, software, seeds, config)

---

## Future / Post-Submission

- NVIDIA NeMo Agent Toolkit integration for agent orchestration
- Reinforcement-learning model router
- Online learning for quality threshold calibration
- Dashboard (Phase-3)
