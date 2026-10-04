# CLAUDE.md — Engineering Intelligence Hub (EIH)

Context for AI assistants and new contributors. Read this before changing anything.

## Session routine (Claude: do this automatically, on both laptops)

The two laptops share context only through this repository, so every Claude session
follows this routine without being asked.

**At the start of a session, before any other work:**
1. Identify the laptop from `EIH_MACHINE_ID` in `.env` (`laptop-a` or `laptop-b`). If
   there is no `.env` yet, ask which laptop this is.
2. Run `git fetch`, then `git status -sb`.
   - On `master` with no uncommitted changes: `git pull`.
   - On another branch, or with uncommitted changes: do **not** switch branches or pull.
     Report the state and ask how to proceed.
3. Read `PROGRESS-A.md` and `PROGRESS-B.md` (newest entries first).
4. Give the user a short summary: what each laptop did last, anything blocked, and the
   suggested next task for *this* laptop. Then wait for the user's go-ahead.

**When the user says they are done for the session** ("done for today", "wrap up",
"that's it" and similar), or before a long pause:
1. Add a dated entry to this laptop's PROGRESS file (done / measured / next / blocked;
   real numbers only).
2. Commit it on the current feature branch (or a new `docs/progress-<date>` branch;
   never on `master`).
3. Show `git log --oneline -5` and `git status -sb`, and **ask before pushing**. After
   the push, explain how to open the PR.

Never force-push, rewrite pushed history, push directly to `master`, change repository
visibility, or delete anything (files, branches, containers, data) without asking.

## What this project is

B.Tech CSE (AI/ML) major project, UPES Dehradun. Research title:
**Task-Aware, Quality-Constrained RAG for Software Engineering: Optimising Quality,
Cost, Latency, Energy and Carbon Footprint.**

EIH classifies each engineering question (SDLC stage, task type, complexity,
criticality) and spends only as much retrieval and model capacity as that task
needs, while **quality is a hard constraint**: a verification gate scores every
answer, failures escalate (wider retrieval → graph → cross-encoder rerank), and if
evidence is still insufficient the system refuses with `INSUFFICIENT EVIDENCE`.

```
minimise  α·Time + β·Cost + γ·Energy + δ·CO₂e + ε·Rework
subject to Quality ≥ task-specific threshold
```

Evaluation is a five-system ablation ladder — **A** LLM-only → **B** fixed hybrid
RAG → **C** + task-aware adaptive retrieval → **D** + knowledge graph → **E** +
quality gate & bounded escalation — reporting a quality/latency/energy/cost/CO₂e
Pareto frontier. Headline metric: **CO₂e per *successful* task**.

Key documents: `docs/PROJECT_REPORT.md` (status and methodology),
`docs/MASTER_DATASET_SPECIFICATION.md` (datasets, evaluation modes R/Q/P),
`M5_RESEARCH_VALIDITY_AUDIT.md`, `RESEARCH_NOTES.md` (decision log), `ROADMAP.md`.

## Non-negotiable rules

1. **Never fabricate or "estimate" results.** Every number reported must come from
   a run that actually executed. Label tiers as MEASURED / ESTIMATED / DERIVED.
2. **Mock-LLM output is not evidence.** `MockLLMProvider` is for unit tests only.
3. **Do not touch the held-out test split** (`benchmark/data/splits_v1.0.json`,
   24 tasks) for tuning, inspection or ad-hoc runs. It runs once, at the end.
4. **A capability must be verified as executing, not just configured.** Four silent
   defects (reranker never ran, BM25 empty, carbon config ignored, rerank energy
   missing) were found this way — see `docs/PROJECT_REPORT.md` §10.5.
5. **Every result records which machine produced it** (`machine_id`, see
   `docs/WORKFLOW.md`) and the grid carbon region used.
6. **Never commit secrets** (`.env`, keys, tokens) or large data (Qdrant snapshots,
   Neo4j dumps, model weights, `.corpus_cache/`). Share data via `C:\EIH_share\`.
7. **No direct pushes to `master`, no force-push, no history rewrites.** Work on
   `feat/<area>` branches and open PRs (see `docs/WORKFLOW.md`).
8. Keep novelty claims conservative (see `PROJECT_REPORT.md` §5.1 "non-claims").

## Hardware — two development laptops

| | Laptop A (Avaneesh) | Laptop B (teammate) |
|---|---|---|
| GPU | RTX 4050 Laptop, 6 GB, Ada (sm_89) | RTX 5050 Laptop, Blackwell (sm_120) — confirm VRAM with `nvidia-smi` |
| CPU | Intel i7-12650H | record in `PROGRESS-B.md` |
| PyTorch | 2.6.0 + cu124 | **must be a cu128 build** (≥ 2.7) — see `SETUP_LAPTOP_B.md` |
| Python | 3.11.9 in `.venv311/` | 3.11 in `.venv311/` |

Energy figures depend on hardware: each laptop sets its own
`EIH_SUSTAINABILITY_CPU_TDP_WATTS` / `EIH_SUSTAINABILITY_GPU_TDP_WATTS` in its
local `.env`. Results from the two laptops are **not directly comparable** for
energy unless the machine is controlled for — never mix them in one table
without a `machine_id` column.

## Two-laptop setup

- Code is shared through GitHub (private repo `kanhaiya27/engineering-intelligence-hub`).
- Data is **not** in git. The Qdrant collection `eih_knowledge` (48,046 chunks) and
  any Neo4j graph are exported to `C:\EIH_share\` and copied to Laptop B; restore
  steps are in `SETUP_LAPTOP_B.md`. Alternatively re-ingest with
  `python -m scripts.ingest_corpus --wave 1`.
- Each person logs their work in `PROGRESS-A.md` / `PROGRESS-B.md`.

## Common commands (PowerShell, from repo root)

```powershell
.\.venv311\Scripts\Activate.ps1
docker compose up -d                      # Qdrant :6333, Neo4j :7474/:7687
python -m pytest                          # 178 tests; 2 need Docker Qdrant running
python -m scripts.ingest_corpus --wave 1  # (re)build the corpus into Qdrant
uvicorn apps.api.main:app --reload --port 8000   # http://localhost:8000/docs
```

## Layout

`ingestion/` loaders + chunkers · `knowledge/` schemas, vector (Qdrant, BGE), graph
(Neo4j) · `retrieval/` dense, BM25, hybrid, reranker, adaptive policy ·
`intelligence/` task classifier · `generation/` LLM providers, RAG pipelines ·
`verification/` quality gate + escalation · `routing/` model routing (not yet wired)
· `sustainability/` energy, cost, carbon · `experiments/m5/` controlled evaluation ·
`benchmark/` tasks + splits · `apps/api/` FastAPI · `scripts/` drivers · `docs/`.

## Current state (2026-10-03)

Phase-2 M1–M5 implemented; P0-1/P0-2 audit fixes applied; wave-1 corpus ingested.
**No real System A–E comparison has been run yet.** Next: local model ladder
(Ollama, Qwen2.5-Coder 1.5B/3B/7B) and routing wiring, P0-3 live calibration,
EIH-SWE annotation. Deadline: experiments complete 25 Oct 2026; final 15 Nov 2026.
See `PROGRESS-A.md`.
