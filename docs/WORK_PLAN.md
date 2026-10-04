# EIH Work Plan — who does what, and when

**Single source of truth for task assignment between the two laptops.**
Last updated: 2026-10-05 (Laptop A). Update the status column whenever a task's PR merges.

## 1. The goal in one paragraph

Build and evaluate a **task-aware, quality-constrained RAG system for software engineering**:
classify each question (SDLC stage, type, complexity, criticality), spend only as much
retrieval and model capacity as it needs, and never return a lower-quality answer to save
energy (verification gate → bounded escalation → explicit refusal). Prove it with a
five-system ablation ladder (**A** LLM-only → **B** fixed hybrid RAG → **C** + adaptive
retrieval → **D** + knowledge graph → **E** + quality gate) on local models only, reporting
quality, latency, **directly measured GPU energy** and CO₂e, with **CO₂e per successful task**
as the headline metric and a quality–energy Pareto frontier. Target venue: a top SE
journal (TOSEM / TSE / EMSE). Details: `docs/PROJECT_REPORT.md`.

## 2. Deadlines

| Date | Deliverable |
|---|---|
| **25 Oct 2026** | Major implementation complete, experiments complete (60-task benchmark, Systems A–E, Pareto + ablations) |
| **15 Nov 2026** | Final paper, final code, final results, reproducibility docs |

## 3. Where we are (phase status, 2026-10-05)

| Phase | Work | Owner | Status |
|---|---|---|---|
| 0 | Foundation, corpus wave 1 (48,046 chunks), retrieval verified, M1–M5 pipeline | A + B | ✅ Done |
| 1a | Environment audit, NVML energy meter, run provenance, VRAM study | A | ✅ Done (branch `feat/local-inference`, PR pending) |
| 1b | OllamaProvider, routing wired into the pipeline, escalation 2→3, long-context probe, GPU job queue | A | 🟡 Next |
| 3 | Knowledge-graph population for the wave-1 repos (System D is identical to C until this exists) | B | ⬜ Not started |
| 4 | Benchmark: retrieval ground-truth labels for the 60 tasks, then EIH-SWE batch 1 | B | ⬜ Not started |
| 5 | Mode R: retrieval metrics (Recall@K, MRR, nDCG) on the 60 tasks | A | ⬜ Blocked on B1 |
| — | P0-3: re-calibrate on the validation split with live local models, re-freeze manifest | A | ⬜ After 1b |
| 6 | Mode Q: Systems A–E on dev/val, then the held-out test once (N=5) | A | ⬜ Blocked on 1b, B4 |
| 10 | Pareto frontier + ablation deltas Δ(A→B)…Δ(D→E) | A | ⬜ After 6 |
| 12 | Report / paper updated with real numbers | B (docs) + A (results) | ⬜ After 6 |
| Web | Project website: overview, live demo of the pipeline, results dashboard | B | ⬜ Skeleton 17–24 Oct, results pages after 25 Oct |
| 2 | Tree-sitter chunking for non-Python languages (RQ6) | B | ⏸ After 25 Oct |
| 3 | Corpus waves 2–4 | B | ⏸ After 25 Oct |
| 7 | Mode P patch + test harness (SWE-bench family) | Member C (TBD) | ⏸ Stretch, not needed for 25 Oct |
| 8 | Scalability / resilience studies | B | ⏸ November |
| 9 | EIH-Fresh contamination-controlled set | B | ⏸ November |
| 11 | Human study (needs ethics approval) | B | ⏸ Optional |

**Rule: only Laptop A produces headline measured results.** Laptop B runs are for
development and smoke tests, written under `experiments/results/**/machine_B/`, and
never mixed into a comparison table.

## 4. Task queues

Each task is one branch and one PR into `master`. Do them in order. Dates are targets.

### Laptop A (Avaneesh, RTX 4050) — owns `routing/` `generation/` `verification/` `experiments/` `retrieval/` `sustainability/`

| # | Branch | Task | Touches | Target |
|---|---|---|---|---|
| A1 | `feat/local-inference` | Phase 1a: `.env` fix, NVML meter, provenance, VRAM study | `core/config.py`*, `sustainability/`, `experiments/`, `scripts/phase1_*`, `CLAUDE.md` | 5 Oct ✅ |
| A2 | `feat/local-inference-routing` | Phase 1b: decide 7B handling; `OllamaProvider`; routing wired with per-call model-id logging; `max_escalation_attempts` 2→3 (manifest hash shown before commit); 20K-token long-context probe; `scripts/job_queue.py` | `generation/`, `routing/`, `verification/`, `scripts/`, `.env.example`* | 11 Oct |
| A3 | `feat/m5-live-calibration` | P0-3 calibration on the 12 validation tasks with live local models; re-freeze manifest | `experiments/m5/` | 14 Oct |
| A4 | `feat/mode-r-retrieval-eval` | Retrieval metrics using B1's labels; re-measure reranker energy in batches (fixes report §10.4) | `evaluation/`*, `retrieval/`, `experiments/` | 16 Oct |
| A5 | `feat/mode-q-systems-a-e` | Systems A–E on dev + val; held-out test once, N=5, via the job queue | `experiments/` | 23 Oct |
| A6 | `feat/pareto-ablation-results` | Pareto frontier, ablation deltas, CO₂e per successful task | `experiments/` | 25 Oct |

### Laptop B (Sanvi, RTX 5050) — owns `ingestion/` `knowledge/graph/` `benchmark/` `apps/` `web/` `docs/`

| # | Branch | Task | Touches | Target |
|---|---|---|---|---|
| B1 | `feat/benchmark-retrieval-labels` | For each of the 60 tasks: relevant files, symbols and line spans (retrieval ground truth). Add the fields to the task schema | `benchmark/data/`, `knowledge/schemas/benchmark.py`* | 10 Oct |
| B2 | `fix/compose-qdrant-healthcheck` | Qdrant image has no `curl`; replace the healthcheck so `docker compose ps` stops showing "unhealthy" | `docker-compose.yml`* | 7 Oct |
| B3 | `feat/graph-populate-wave1` | Populate Neo4j for the 6 wave-1 repos with `EngineeringGraphBuilder`; export a dump to `C:\EIH_share\neo4j.dump` for Laptop A | `knowledge/graph/`, new `scripts/build_graph.py` | 16 Oct |
| B4 | `feat/benchmark-eih-swe-batch1` | EIH-SWE batch 1: 60–100 new human-verified tasks across the wave-1 repos (schema in dataset spec §5) | `benchmark/` | 20 Oct |
| B5 | `docs/report-real-results` | Put A's measured results into `docs/PROJECT_REPORT.md` and the paper draft | `docs/` | 25 Oct → 15 Nov |
| B6 | `feat/web-project-site` | Project website in `web/`, served by the FastAPI app: (1) overview and architecture; (2) live demo — ask a question, see the task classification, retrieval strategy, model tier, quality-gate verdict and measured energy; (3) results dashboard that reads `experiments/results/**/machine_A/*.json` (VRAM study now; A–E Pareto and ablations after A6). Reads A's result files, never edits them | `web/`, `apps/api/` | Skeleton 24 Oct, complete 10 Nov |

`*` = shared file (see §5).

### Dependencies between the queues

- **A4 needs B1** (labels). If B1 is late, A does A3 first.
- **A5 needs B3** (populated graph), otherwise System D is identical to System C and the
  D-vs-C ablation measures nothing. Laptop A restores B's Neo4j dump before A5.
- **B5 needs A5/A6** results.
- **B6 (website) reads A's result JSON.** Laptop A keeps result files stable: every file
  has a top-level `study`, `provenance` and `results` key, and A announces any change to
  that shape in PROGRESS-A before merging it. The live demo uses existing API endpoints
  (`/adaptive/query`); new endpoints go in `apps/api/` (B).

## 5. Collision rules

1. **Stay in your own directories.** Editing the other laptop's directory requires their
   review on the PR.
2. **Shared files** — `core/`, `configs/`, `knowledge/schemas/`, `knowledge/vector/`,
   `evaluation/`, `tests/conftest.py`, `requirements*.txt`, `docker-compose.yml`,
   `.env.example`, `pyproject.toml`, root docs: write a line in your PROGRESS file *before*
   starting, keep the change small, and get the other laptop's review.
3. **Each laptop has its own results folder**: `experiments/results/<study>/machine_A/` or
   `machine_B/`. Never write into the other's.
4. **`docs/` belongs to B**, except `docs/WORK_PLAN.md`, which both update (status column only).
5. **Small PRs, merged often.** `git pull` on `master` before every new branch.
6. **Never** push to `master`, force-push, rewrite pushed history, or delete without asking.

## 6. GitHub routine (both laptops)

Start of work:
```powershell
cd C:\Projects\Majors\engineering-intelligence-hub      # Laptop B: her clone path
git checkout master
git pull
git checkout -b <branch-from-the-table>
```
While working: commit small, logical pieces (`git add <files>`, `git commit -m "feat(area): ..."`).
Finish a task:
```powershell
python -m pytest                      # must pass
git push -u origin <branch>
```
Then on GitHub: **Compare & pull request** → base `master` ← your branch → fill the template
→ ask the other laptop to review → **Merge pull request** (merge commit). Afterwards both
laptops run `git checkout master; git pull`.

Repository: https://github.com/kanhaiya27/engineering-intelligence-hub (private).
