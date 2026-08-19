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

## Development Phases

| Phase | Goal | Target Date | Status |
|---|---|---|---|
| **Phase-0 (Foundation)** | Repository structure, schemas, interfaces, tests | August 2026 | ✅ Complete |
| **Phase-1 (Core Baseline RAG)** | Repository ingestion, GPU embeddings, Qdrant, hybrid retrieval, baseline RAG, 60-task benchmark, evaluation suite | August 2026 | ✅ Complete |
| **Phase-2 (Adaptive RAG)** | Task classification, adaptive retrieval routing, model routing, quality gate | October 2026 | ⏳ Planned |
| **Phase-3 (Experiments)** | Baselines A–F, ablations, Pareto analysis | October 2026 | ⏳ Planned |
| **Phase-4 (Graph + Agents)** | Knowledge graph, agentic orchestration | November 2026 | ⏳ Planned |

See [ROADMAP.md](ROADMAP.md) for detailed milestone breakdown.

---

## Six-Month Deadlines

| Date | Deliverable |
|---|---|
| **25 August 2026** | Research PPT (title, literature review, novelty, architecture, expected output type) |
| **15 September 2026** | Research paper draft, baseline system working, initial benchmark, evaluation framework |
| **25 October 2026** | Major implementation complete, experiments complete, updated research |
| **15 November 2026** | Final paper, final code, final experiments, final results, reproducibility docs |

---

## Quick Start (Phase-1 Baseline RAG)

```bash
# 1. Activate virtual environment
cd c:\Projects\Majors\engineering-intelligence-hub
.\.venv311\Scripts\activate

# 2. Run Qdrant Vector Store
docker-compose up -d qdrant

# 3. Ingest a repository (or single file via REST API)
# REST API: POST /ingest/repository or POST /ingest/file

# 4. Run test suite (90/90 tests passing)
pytest tests/ -v

# 5. Start API server
uvicorn apps.api.main:app --reload --port 8000
# Visit http://localhost:8000/docs
# Test /health, /info, /ingest/file, /retrieve, /query
```

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.8+ (3.11+ recommended) |
| API | FastAPI + Uvicorn |
| Schemas | Pydantic v2 |
| Vector Store | Qdrant (Phase-1) |
| Graph Store | Neo4j (Phase-1) |
| Embeddings | BAAI/bge-small-en-v1.5 (Phase-1) |
| LLM Providers | OpenAI, Anthropic, Google, Local (Ollama) |
| Logging | Loguru (structured JSONL) |
| GPU | NVIDIA RTX 4050 (CUDA 12.1) |
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

See [docs/development_phases.md](docs/development_phases.md) for contribution guidelines per phase.

---

## Licence

MIT — see LICENCE file.
