# CLAUDE.md — Engineering Intelligence Hub (EIH)

Context for AI assistants and new contributors. Read this before changing anything.

## Session routine (Claude: do this automatically)

**One person, one laptop (laptop-a), since 2026-10-05.** There is no second laptop and
no task split (WORK_PLAN change C11). GitHub is a private backup only.

**At the start of a session, before any other work:**
1. `git fetch`; report the branch and whether anything is uncommitted. On `master` with a
   clean tree: `git pull`. On a feature branch: `git merge origin/master` (never rebase).
   With uncommitted changes: do not switch branches or pull; report and ask.
2. Read `PROGRESS-A.md` (newest first) and the ordered work list in `docs/WORK_PLAN.md` §3.
3. Tell Avaneesh in plain words what was done last and what the next step is, then wait.

**When starting a step:** from up-to-date `master`, create a branch for it. Never commit
on `master`.

**When Avaneesh says he is done for the session**, or a step is finished: run
`python -m pytest` and report the real result; add a dated `PROGRESS-A.md` entry (done /
measured / next / blocked; real numbers only); commit on the feature branch; push the
feature branch (standing permission); give the PR link
`https://github.com/kanhaiya27/engineering-intelligence-hub/pull/new/<branch>`.

**The plan:** the original plan is frozen in `docs/original_plan.md` (+ the dataset
specification). `docs/WORK_PLAN.md` lists the work in order; every deviation goes into its
change register, and nothing from the original plan is dropped without Avaneesh's decision.

Never force-push, rewrite pushed history, push directly to `master`, or change repository
visibility.

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

Key documents: **`docs/original_plan.md` (the frozen original plan)**, **`docs/WORK_PLAN.md`
(ordered work list, status, change register — check it before starting any step)**,
`docs/PROJECT_REPORT.md` (status and methodology),
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
5. **Every result records which machine produced it** (`machine_id` from `.env`) and the
   grid carbon region used.
6. **Never commit secrets** (`.env`, keys, tokens) or large data (Qdrant snapshots,
   Neo4j dumps, model weights, `.corpus_cache/`). Data backups live in `C:\EIH_share\`.
7. **No direct pushes to `master`, no force-push, no history rewrites.** Work on
   `feat/<area>` / `fix/<area>` branches and open PRs.
8. Keep novelty claims conservative (see `PROJECT_REPORT.md` §5.1 "non-claims").

## Hardware (laptop-a — the only machine that produces results)

| | |
|---|---|
| GPU | RTX 4050 Laptop, 6 GB, Ada (sm_89), driver 617.14 |
| CPU | Intel i7-12650H |
| PyTorch | 2.6.0 + cu124 |
| Python | 3.11.9 in `.venv311/` |

Energy figures are hardware-specific (`EIH_SUSTAINABILITY_*_TDP_WATTS` in `.env`).
Earlier laptop-b work (Sep–Oct 2026) is archived in `docs/archive/`.

### Local model ladder (Ollama) — pinned by digest

Every result must cite the digest of the model that produced it. Recorded on Laptop A
on 2026-10-04 with Ollama 0.35.1 (`curl http://localhost:11434/api/tags`):

| Tier | Ollama tag | Params / quant | Size (bytes) | Digest (sha256) |
|---|---|---|---|---|
| small | `qwen2.5-coder:1.5b` | 1.5B Q4_K_M | 986,062,089 | `d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668` |
| medium | `qwen2.5-coder:3b` | 3.1B Q4_K_M | 1,929,912,626 | `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225` |
| large | `qwen2.5-coder:7b` | 7.6B Q4_K_M | 4,683,087,561 | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` |

If `ollama pull` ever changes a digest, the model changed: results from different
digests are not comparable. **How** the models are called (num_ctx, num_gpu, temperature,
seed, output limit) is defined once, in `configs/inference.yaml`.

## Data

- Code: private GitHub repo `kanhaiya27/engineering-intelligence-hub` (backup).
- Data is **not** in git: Qdrant collection `eih_knowledge_v2` (53,905 chunks, Qdrant 1.15.1;
  the old `eih_knowledge` with 48,046 is kept; snapshot in `C:\EIH_share\`), Neo4j graph.
  The collection name comes only from `EIH_VECTOR_COLLECTION_NAME` (`.env`). Re-ingest with
  `python -m scripts.ingest_corpus --wave 1`.
- Work log: `PROGRESS-A.md`.

## Common commands (PowerShell, from repo root)

```powershell
.\.venv311\Scripts\Activate.ps1
docker compose up -d                      # Qdrant :6333, Neo4j :7474/:7687
python -m pytest                          # full suite; a few tests need Docker Qdrant/Neo4j and Ollama
python -m scripts.ingest_corpus --wave 1  # (re)build the corpus into Qdrant
uvicorn apps.api.main:app --reload --port 8000   # http://localhost:8000/docs
```

## Layout

`ingestion/` loaders + chunkers · `knowledge/` schemas, vector (Qdrant, BGE), graph
(Neo4j) · `retrieval/` dense, BM25, hybrid, reranker, adaptive policy ·
`intelligence/` task classifier · `generation/` LLM providers, RAG pipelines ·
`verification/` quality gate + escalation · `routing/` model routing (System E_routed, RQ4)
· `sustainability/` energy, cost, carbon · `experiments/m5/` controlled evaluation ·
`benchmark/` tasks + splits · `apps/api/` FastAPI · `scripts/` drivers · `docs/`.

## Current state (2026-10-05, after the restore-original-plan audit)

Phase 0 and Phase 1 done: wave-1 corpus (6 repos, 48,046 chunks), local models
(Qwen2.5-Coder 1.5B/3B/7B) measured, job queue, single config `configs/inference.yaml`.
Measurement and validity fixes on `restore-original-plan` (real classifier for C–E, plan
§9.1 tiers, CPU estimate, §9.2 latency breakdown, RQ4 routed system). Knowledge graph built
(own builder, AST + Git history; 37,066 nodes / 58,982 edges in Neo4j; `python -m scripts.build_graph
--wave 1 --reset`). **No real System A–E
comparison has been run yet.** Deadlines: experiments complete 25 Oct 2026; final 15 Nov 2026.

## Measurement rules learned the hard way (Laptop A, RTX 4050, driver 617.14)

- Energy = NVML energy counter read **only at start and end** of a block. Polling GPU
  power (or the counter) during a measurement inflates the reading by 9–100+ W.
  Use `sustainability/energy/nvml_meter.py`; never write a new power-polling loop.
- The counter updates in ~100 ms steps: energy for operations shorter than a few
  seconds is not measurable per call — measure batches.
- Idle power is ~3–6 W only while some process holds a CUDA context; with none it sits
  at ~27–31 W (P0). Report **gross** energy as the headline; "net of idle" only with a
  settled P8 baseline.
- 7B (Q4_K_M) runs 82% on GPU at num_ctx 4096 (Ollama's own estimate), even alone.
- **Run settings (decided 2026-10-05, defined in `configs/inference.yaml`): num_ctx 12,288,
  `num_gpu 999` (all layers on the GPU) for every model, output limit 1,024 tokens.** The 7B fits at 12K (peak 5,906 of
  6,141 MiB with encoders); at 16K VRAM is full; from 20K the driver silently pages to
  system RAM (5–7× slower, 4–7× the energy) while Ollama still reports "100% on GPU".
  See `experiments/results/phase1/machine_A/long_context_probe.md`.
- Long runs: work up to 90 °C; above that, cool to 65 °C and repeat the measurement.
- The laptop throttles at 84–87 °C; long runs need cooldowns and logged temperatures.
