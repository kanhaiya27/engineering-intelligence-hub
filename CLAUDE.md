# CLAUDE.md — Engineering Intelligence Hub (EIH)

Context for AI assistants and new contributors. Read this before changing anything.

## Session routine (Claude: do this automatically, on both laptops)

The two laptops work **at the same time** and share context only through this
repository, so every Claude session follows this routine without being asked. Claude
handles all git commands; the user only approves pushes and merges PRs on GitHub.

**Automatic guard (hooks in `.claude/settings.json`, script `scripts/git_sync_guard.py`):**
- At session start it runs `git fetch` and reports which commits the other laptop merged
  into `origin/master` that this checkout lacks. Its report arrives in your context as
  "[git sync guard]". **Tell the user this status first, before anything else.**
- While `origin/master` holds a **must-pull** change this branch lacks (a commit tagged
  `[must-pull]`, or any change to a shared file), **edits to repo files are blocked**.
  Do not work around the block (never edit via Bash/sed instead): tell the user, sync,
  re-run the tests, then continue.

**At the start of a session, before any other work:**
1. Identify the laptop from `EIH_MACHINE_ID` in `.env` (`laptop-a` or `laptop-b`). If
   there is no `.env` yet, ask which laptop this is.
2. Report the guard's status. Then sync safely:
   - On `master`, nothing uncommitted: `git pull`.
   - On a feature branch: `git fetch` then `git merge origin/master` (never rebase), and
     run `python -m pytest` if anything shared changed.
   - With uncommitted changes: do not switch branches or pull. Report and ask.
3. Read `PROGRESS-A.md`, `PROGRESS-B.md` (newest first) and this laptop's queue in
   `docs/WORK_PLAN.md`.
4. Give the user a short summary: what each laptop did last, anything blocked, and the
   next task for *this* laptop. Then wait for the user's go-ahead.

**When starting a task:** from up-to-date `master`, create the branch named in
`docs/WORK_PLAN.md` (`git checkout -b <branch>`). Never commit on `master`.

**Marking must-pull changes (so the other laptop gets warned and blocked):** if a commit
changes a shared file (`core/`, `configs/`, `knowledge/schemas/`, `knowledge/vector/`,
`evaluation/`, `tests/conftest.py`, `requirements*.txt`, `pyproject.toml`,
`docker-compose.yml`, `.env.example`, `.gitignore`, `.gitattributes`, `.claude/`,
`CLAUDE.md`, `scripts/git_sync_guard.py`) or changes how the other laptop must work,
end its subject with ` [must-pull]` and add a line to this laptop's PROGRESS file
under "Must pull". The guard also catches untagged shared-file changes automatically.

**When the user says they are done for the session** ("done for today", "wrap up",
"that's it" and similar), or a task is finished:
1. Run `python -m pytest`; report the real result.
2. Add a dated entry to this laptop's PROGRESS file (done / measured / next / blocked /
   must pull; real numbers only).
3. Commit on the current feature branch (never on `master`), tagging `[must-pull]` where
   the rule above applies.
4. Show `git log --oneline -5` and `git status -sb`, and **ask before pushing**.
5. After the push, give the PR link
   (`https://github.com/kanhaiya27/engineering-intelligence-hub/pull/new/<branch>`) and
   tell the user to send the other laptop: "merged <branch>" once it is merged — plus
   "MUST PULL before working" if the push contains a `[must-pull]` commit.

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

Key documents: **`docs/WORK_PLAN.md` (who does what, phase status, task queues per
laptop — check it before starting any task)**, `docs/PROJECT_REPORT.md` (status and methodology),
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

### Local model ladder (Ollama) — pinned by digest

Every result must cite the digest of the model that produced it. Recorded on Laptop A
on 2026-10-04 with Ollama 0.35.1 (`curl http://localhost:11434/api/tags`):

| Tier | Ollama tag | Params / quant | Size (bytes) | Digest (sha256) |
|---|---|---|---|---|
| small | `qwen2.5-coder:1.5b` | 1.5B Q4_K_M | 986,062,089 | `d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668` |
| medium | `qwen2.5-coder:3b` | 3.1B Q4_K_M | 1,929,912,626 | `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225` |
| large | `qwen2.5-coder:7b` | 7.6B Q4_K_M | 4,683,087,561 | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` |

If `ollama pull` ever changes a digest, the model changed: results from different
digests are not comparable. Laptop B must show the same digests before its runs count.

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

## Current state (2026-10-05)

Phase-2 M1–M5 implemented; P0-1/P0-2 audit fixes applied; wave-1 corpus ingested
(48,046 chunks). Phase 1a done on Laptop A: `.env` settings bug fixed, NVML energy
meter, run provenance, measured VRAM study (`experiments/results/phase1/machine_A/`).
**No real System A–E comparison has been run yet.** Next per `docs/WORK_PLAN.md`:
Laptop A → Phase 1b (OllamaProvider + routing); Laptop B → retrieval labels for the
60 tasks, Qdrant healthcheck fix, knowledge-graph population. Deadlines: experiments
complete 25 Oct 2026; final 15 Nov 2026.

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
- The laptop throttles at 84–87 °C; long runs need cooldowns and logged temperatures.
