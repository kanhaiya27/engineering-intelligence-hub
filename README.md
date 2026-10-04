# Engineering Intelligence Hub

**Task-Aware Energy-Efficient RAG for Software Engineering:**
*Optimising Quality, Cost, Latency, Energy and Carbon Footprint*

---

## Overview

Engineering Intelligence Hub (EIH) is a research-oriented, developer-focused RAG and agentic system designed to:

1. **Understand software repositories** — source code, documentation, architecture, issues, commits, tests, and incidents.
2. **Investigate energy-efficiency trade-offs** — empirically studying whether software-engineering AI tasks can be completed with lower latency, cost, energy consumption, and CO₂e while maintaining a predefined task-specific quality threshold.

> **Research Principle:** The system must NEVER intentionally sacrifice answer quality merely to save energy. Quality is a hard constraint, not an objective. The objective is to minimise resource consumption *subject to* quality being met.

---

## Research Question

> *"Can a task-aware, quality-constrained engineering intelligence system reduce developer effort, rework, latency, computational cost, energy consumption, and CO₂ emissions across software-engineering tasks while maintaining acceptable engineering quality, reliability, and security?"*

---

## System Architecture

```
User Task
    ↓
Task Classification
    ↓
Task Complexity / Criticality / Risk
    ↓
Required Quality Threshold
    ↓
Adaptive Retrieval Strategy
    ↓
Model / Agent Selection
    ↓
Generation
    ↓
Quality / Grounding / Verification
    ↓
PASS → Output
FAIL → Escalate → Stronger retrieval / model → Re-evaluate
```

### Optimisation Objective

```
minimise:   α·Time + β·Cost + γ·Energy + δ·CO₂e + ε·Rework
subject to: Quality ≥ task_specific_threshold
            Reliability ≥ required_threshold      (where measurable)
            SecurityRisk ≤ allowed_threshold      (where measurable)
```

---

## Repository Structure

```
engineering-intelligence-hub/
├── apps/api/           FastAPI REST API
├── agents/             Agentic orchestration (Phase-2+)
├── ingestion/          Knowledge ingestion pipeline
├── knowledge/
│   ├── schemas/        Pydantic data models (artifacts, tasks, benchmark)
│   ├── vector/         Vector store interface
│   └── graph/          Graph store interface
├── retrieval/          Retrieval strategy layer
├── routing/            Model capability registry + routing
├── generation/         LLM provider abstraction
├── verification/       Quality gate + evaluators
├── sustainability/
│   ├── energy/         Energy estimation
│   ├── cost/           Monetary cost estimation
│   └── carbon/         CO₂e estimation
├── evaluation/         Evaluation metrics + scorers
├── experiments/        Experiment configs, logger, runner
├── benchmark/          Benchmark pipeline (generation, validation)
├── datasets/           Open-source repository registry
├── configs/            YAML configuration files
├── core/               Cross-cutting: config, logging, exceptions
├── scripts/            Utility scripts
├── tests/              pytest test suite
└── docs/               Extended documentation
```

---

## Status (5 October 2026)

| Area | Status |
|---|---|
| Ingestion, BGE embeddings (GPU), Qdrant, BM25, hybrid retrieval, cross-encoder reranker | ✅ Implemented and verified |
| Task intelligence, knowledge-graph code, adaptive retrieval, quality gate + escalation | ✅ Implemented (graph not yet populated) |
| M5 controlled evaluation framework (manifest, splits, metrics, Pareto) + P0 audit fixes | ✅ Implemented |
| Corpus wave 1: 6 Python repositories, 48,046 chunks | ✅ Ingested |
| Local model ladder (Ollama, Qwen2.5-Coder 1.5B / 3B / 7B) + measured VRAM/energy study | ✅ Phase 1a done |
| OllamaProvider + model routing in the pipeline | 🟡 Phase 1b, in progress |
| Real System A–E results, Pareto frontier, ablations | ⬜ Not run yet — no comparison is claimed |

**Who does what, by when:** [docs/WORK_PLAN.md](docs/WORK_PLAN.md).
Milestones: [ROADMAP.md](ROADMAP.md). Team workflow: [docs/WORKFLOW.md](docs/WORKFLOW.md).
Methodology and measured status: [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md).

---

## Six-Month Deadlines

| Date | Deliverable |
|---|---|
| **25 August 2026** | Research PPT (title, literature review, novelty, architecture, expected output type) |
| **15 September 2026** | Research paper draft, baseline system working, initial benchmark, evaluation framework |
| **25 October 2026** | Major implementation complete, experiments complete, updated research |
| **15 November 2026** | Final paper, final code, final experiments, final results, reproducibility docs |

---

## Quick Start (Windows, PowerShell)

New laptop: follow [SETUP_LAPTOP_B.md](SETUP_LAPTOP_B.md) first.

```powershell
cd C:\Projects\Majors\engineering-intelligence-hub
.\.venv311\Scripts\Activate.ps1

# Databases (Docker Desktop running). On Laptop A use `docker start eih-qdrant eih-neo4j`
# until its Qdrant volume is upgraded — see PROGRESS-A.md.
docker compose up -d

python -m pytest                               # 200+ tests; 2 need Qdrant running
python -m scripts.ingest_corpus --wave 1       # (re)build the corpus into Qdrant
python -m scripts.phase1_vram_study            # measured VRAM / throughput / energy study
uvicorn apps.api.main:app --reload --port 8000 # http://localhost:8000/docs
```

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| API | FastAPI + Uvicorn |
| Schemas | Pydantic v2 |
| Vector Store | Qdrant 1.15 |
| Graph Store | Neo4j 5.18 |
| Embeddings / reranker | BAAI/bge-small-en-v1.5, cross-encoder/ms-marco-MiniLM-L-6-v2 |
| LLMs | **Local only**, via Ollama: Qwen2.5-Coder 1.5B / 3B / 7B (Q4_K_M, pinned by digest in CLAUDE.md) |
| Energy / carbon | NVML energy counter (MEASURED); region-aware CO₂e (India grid, 713 gCO₂e/kWh) |
| Logging | Loguru (structured JSONL) |
| GPUs | Laptop A: RTX 4050 6 GB (headline results) · Laptop B: RTX 5050 8 GB (development) |
| Containers | Docker + Docker Compose |
| Experiments | JSONL logs + pandas/DuckDB analysis |

---

## Research Honesty Principles

- Do not claim novelty beyond what the evidence supports.
- Do not fabricate energy, CO₂, or quality results.
- Always disclose system boundaries for sustainability estimates.
- Always document carbon intensity values and regions used.
- Label proposed research metrics as *proposed* — not established standards.
- Human approval is required before tasks enter the official benchmark.

---

## Contributing

Two laptops share this private repository. Read [CLAUDE.md](CLAUDE.md) and
[docs/WORKFLOW.md](docs/WORKFLOW.md): work on `feat/<area>-<what>` branches, open a Pull
Request into `master`, never push to `master` directly, and record `machine_id` on every result.

---

## Licence

MIT — see LICENCE file.
