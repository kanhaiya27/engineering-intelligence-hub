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

### Phase-1 Goals (by 15 September 2026)

- [ ] **Ingestion pipeline** — GitHub REST API loader for commits, issues, PRs; file loaders for Python, Markdown, YAML
- [ ] **Embedding** — BAAI/bge-small-en-v1.5 (local CUDA) + tiktoken for token counting
- [ ] **Vector store** — Qdrant integration (`QdrantVectorStore` implementing `BaseVectorStore`)
- [ ] **Hybrid retrieval** — Dense + BM25 fusion; concrete `HybridRetriever`
- [ ] **LLM providers** — `OpenAIProvider` and `AnthropicProvider`
- [ ] **Baselines A and B** — LLM-only and Fixed RAG + fixed model
- [ ] **Initial benchmark** — 100 development tasks across 2 repositories (CANDIDATE status)
- [ ] **Evaluation framework** — Correctness + groundedness + relevance evaluators
- [ ] **Sustainability instrumentation** — All calls instrumented with energy/cost/CO₂ estimates
- [ ] **Docker Compose** — Qdrant + Neo4j services

---

## Milestone 3 — Major Implementation + Experiments (25 October 2026)

### Phase-2 Goals

- [ ] **Task classifier** — Rule-based + lightweight LLM-based classifier
- [ ] **Adaptive retrieval router** — Full `RetrievalRouter` with YAML-driven strategy resolution
- [ ] **Tier-based model router** — `TierBasedRouter` implementing `BaseModelRouter`
- [ ] **Quality gate active** — Groundedness + relevance evaluators integrated
- [ ] **Escalation logic** — Full PASS/ESCALATE/FAIL pipeline
- [ ] **Baselines C, D, E, F** — All six named baselines running
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
