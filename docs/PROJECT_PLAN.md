# EIH Project Plan: Status, Remaining Work and Two-Laptop Split

**Last updated:** 2026-10-05 · **Owner of this file:** both laptops (changes by PR)

This file is the single place for **where we are**, **what is left**, and **which
laptop does what**. If it conflicts with an older document, this one wins and the
older one should be fixed. Rules (no fabricated numbers, the held-out split runs
once, verify capabilities execute, record `machine_id`) are in `CLAUDE.md` and are
not repeated here.

---

## 1. Final goal (unchanged)

A research system and paper: **Task-Aware, Quality-Constrained RAG for Software
Engineering.** EIH classifies each engineering question and spends only the
retrieval and model capacity the task needs. Quality is a hard constraint:
answers are verified, failures escalate, and if evidence is still insufficient
the system refuses.

Deliverables:

1. **Research results:** a five-system ablation ladder (A LLM-only → B fixed
   hybrid RAG → C + task-aware retrieval → D + knowledge graph → E + quality gate
   and escalation) on our EIH-SWE benchmark and external datasets. Output is a
   quality/latency/energy/cost/CO₂e Pareto frontier, with headline metric
   **CO₂e per successful task**, answering RQ1–RQ8 (`docs/PROJECT_REPORT.md` §3).
2. **Final paper**, plus reproducibility package (manifest, seeds, hardware,
   `machine_id`).
3. **Public web platform** (the "real site"): a web app where a visitor asks an
   engineering question and sees the full pipeline trace. That means
   classification, retrieved code with `file:line` citations, quality-gate
   verdict, escalation steps and energy/CO₂e with MEASURED/ESTIMATED/DERIVED
   labels. It also shows the published experiment results.

Deadlines (`README.md`): **25 Oct 2026** major implementation and experiments
complete · **15 Nov 2026** final paper, code, results, reproducibility.

---

## 2. Where we are now

**Milestone 3 (due 25 Oct), at the "pre-experiment gate".** All components are
implemented, and the suite has 178 tests passing on `master`. **No real System
A–E comparison has run yet.** Every quality number on disk came from the mock
LLM, which is not evidence.

What blocks the first real run:

| Blocker | Why it blocks | Owner |
|---|---|---|
| **F1: escalation is inert.** Escalated strategies silently fall back to `hybrid` (verified by execution on laptop-b, 2026-10-04; see `docs/API_CONTRACT.md` §8) | Any System E result would be invalid | A |
| No local model ladder (Ollama + Qwen2.5-Coder 1.5B/3B/7B) | Locked decision: local models only. Nothing real can be generated | A |
| **Knowledge graph is empty** (Neo4j has only a 2-node test fixture) | System D would behave exactly like C, so Δ(C→D) would be meaningless | B |
| P0-3 calibration on the validation split with a live model | Required before freezing the manifest (`M5_RESEARCH_VALIDITY_AUDIT.md`) | A |
| Benchmark has 60 tasks; target is 400–500 (`MASTER_DATASET_SPECIFICATION.md` §1) | Statistical power for RQ1/RQ3/RQ5 | A + B |
| Licence audit not done | Blocks downloading any external dataset | B |

### 2.1 Phase numbering (old documents disagree)

Four documents number phases differently. From now on we use **milestones +
work items (A1…, B1…, J1…)** from §4. Mapping:

| Old name | Meaning | Status |
|---|---|---|
| README Phase-0 / Phase-1, ROADMAP Milestone 1–2 | Foundation, baseline RAG, 60-task benchmark | ✅ done |
| README Phase-2, ROADMAP Phase-2 M1–M5 | Task intelligence, KG code, adaptive retrieval, quality gate, M5 evaluation framework | ✅ code done (but see F1) |
| ROADMAP "Phase-3 goals": Neo4j store, graph-augmented retrieval | Code | ✅ done |
| ROADMAP "Phase-3 goals": KG population | Data | ❌ → **B4** |
| PROJECT_REPORT §11 phases 1, 5, 6, 10 | Model ladder, Mode R, Mode Q, final eval | ❌ → A4–A11 |
| PROJECT_REPORT §11 phases 2, 3, 8, 9 | Multi-language chunking, corpus waves 2–4, systems studies, EIH-Fresh | ❌ → B8–B10 |
| PROJECT_REPORT §11 phase 7 (Member C) | Mode P patch harness | ❌ **unassigned**, see decision D6 |
| "Phase 8 web backend" (session instruction, 2026-10-04) | Web platform | in progress → **B3, B7, B11** |

### 2.2 Done since 2026-10-03

- Laptop B set up and verified: RTX 5050 8 GB, torch 2.11.0+cu128, Qdrant
  restored (48,046 points), 178 tests passing (`PROGRESS-B.md`).
- **API contract v1** (`docs/API_CONTRACT.md`, branch `feat/api-contract`,
  awaiting review by both laptops). This is the frozen interface between
  pipeline and website, with 31 contract tests (209 total on laptop-b).
- Review findings for Laptop A: **F1** (escalation fallback, verified by
  execution) and **F2–F5** (energy provenance, by code inspection).

---

## 3. Directory ownership (no collisions)

Each laptop **only edits its own directories**. Anything in a shared directory
goes through a PR that both review, announced first in the PROGRESS file under
"Heads-up".

| Laptop A (Avaneesh, RTX 4050 6 GB) | Laptop B (RTX 5050 8 GB) | Shared (both review) |
|---|---|---|
| `routing/` `generation/` `verification/` `experiments/` `retrieval/` `sustainability/` | `ingestion/` `knowledge/graph/` `benchmark/` `apps/` `web/` `docs/` | `core/` `configs/` `intelligence/` `knowledge/schemas/` `knowledge/vector/` `evaluation/` `scripts/` `tests/`, root files, **`apps/api/contract/`** (joint) |

Collision-proof conventions:

- **Tests.** Add *new* test files only in your own area. A uses
  `tests/test_{generation,retrieval,verification,experiments,sustainability,routing}/`.
  B uses `tests/test_{api,ingestion,knowledge,benchmark,web}/`. Never edit the
  other laptop's test files.
- **`core/config.py` and `configs/*.yaml`.** Only one open PR at a time touches
  them. Announce in PROGRESS → Heads-up. Planned: A adds `EIH_MACHINE_ID` to
  `core/config.py` (A6); B reads it and does not add its own.
- **`scripts/`.** New files are prefixed by area (`scripts/graph_*.py` B,
  `scripts/run_*.py` A).
- **Benchmark tasks.** Each annotator writes their own batch files:
  `benchmark/data/eih_swe/batch_A_###.json` and `batch_B_###.json`. They are
  merged only by `benchmark/` tooling (B).
- **Results.** `experiments/results/<experiment>/<machine_id>/…`. Never mix
  machines in one table without a `machine_id` column.
- **Data, not git.** Qdrant snapshots and Neo4j dumps go via `C:\EIH_share\`.
  Whoever produces one notes its SHA256 in their PROGRESS file.
- **Contract.** `apps/api/contract/` changes need approval from both (snapshot
  test enforces this).

---

## 4. Work items

Priority: **P0** critical path for 25 Oct · **P1** needed for 15 Nov · **P2**
stretch. Nothing has been removed from scope; P2 items still run if time allows,
otherwise they are reported as future work.

### 4.1 Laptop A (pipeline, experiments)

| ID | Pri | Work | Branch | Done when (verifiable) |
|---|---|---|---|---|
| **A1** | P0 | Fix F1: escalated attempts must execute the escalated config. Pass the `RetrievalStrategyConfig` object instead of its name, or register it | `fix/verification-escalation-strategy` | Test: for each rung, the executed `top_k`/graph/rerank equals the requested values; `resolved_strategy` equals the requested name |
| **A2** | P0 | Expose per-attempt objects (`RetrievalResult`, `GenerationResponse`, `QualityReport`, strategy) from `QualityAwareRAGPipeline`. Add `ExperimentMode.SYSTEM_E` and a System-A (no retrieval) path | `feat/generation-attempt-trace` | B's adapter can build a valid contract `PipelineTrace` for A–E |
| **A3** | P0 | Fix F2–F5: NVML fallback label, `is_local_model`, CPU utilisation window. Decide the F3 tier | `fix/sustainability-energy-provenance` | Tests cover the fallback path; the method label matches what ran |
| **A4** | P0 | Ollama provider + Qwen2.5-Coder 1.5B / 3B / 7B-Q4 on the RTX 4050; record VRAM per model | `feat/generation-ollama-ladder` | One real generation per model logged with NVML energy and `machine_id` |
| **A5** | P0 | Wire `routing/` into the pipeline (RQ4) | `feat/routing-wire-ladder` | Trace shows the routed `model_id` differing by task class |
| **A6** | P0 | `EIH_MACHINE_ID` in `core/config.py`; experiment logger writes machine_id, GPU, torch/CUDA, git SHA automatically | `feat/experiments-machine-id` | Every result manifest carries them |
| A7 | P0 | Decide `max_escalation_attempts` 2 → 3 (D5), after A1 | (in A1 PR) | Manifest updated |
| **A8** | P0 | P0-3 calibration on the **validation** split with the live local model; re-freeze manifest | `feat/experiments-p0-3-calibration` | New frozen manifest hash in PROGRESS-A |
| A9 | P0 | **Mode R** runs (RepoBench, CrossCodeEval slices) once B5 delivers loaders | `feat/experiments-mode-r` | Recall@K / MRR / NDCG per system, laptop-tagged |
| **A10** | P0 | **Mode Q** dev/val runs, Systems A–E, on one machine (D1) | `feat/experiments-mode-q` | Results directory + Pareto plot (dev/val only) |
| A11 | P1 | **Final held-out test run, once** (N=5), Pareto frontier, ablation deltas Δ(A→B)…Δ(D→E) | `feat/experiments-final-test` | Frozen results; never re-run for tuning |
| A12 | P1 | Export real traces from A10/A11 runs (via A2 objects) for the website's cached mode | (with A10) | JSON files that pass the contract tests, copied via `C:\EIH_share\` |
| A13 | P1 | Large-LLM baseline (D4) | — | Decision recorded and run |

### 4.2 Laptop B (data, graph, benchmark, website)

| ID | Pri | Work | Branch | Done when (verifiable) |
|---|---|---|---|---|
| B1 | P0 | API contract v1 merged (review by A) | `feat/api-contract` | PR merged |
| **B2** | P0 | Licence audit of every dataset in the master spec, from official sources only; unverified items marked UNVERIFIED | `docs/licence-audit` | `docs/LICENCE_AUDIT.md` reviewed |
| **B3** | P0 | Web backend hardening (CORS, rate limits, input limits, request IDs, health, structured PII-free logs, untrusted-text handling, no internal paths) + `/v1/trace` and `/v1/trace/stream` with mock and cached fallback | `feat/web-backend` | Contract tests, rate-limit tests, end-to-end smoke test pass |
| **B4** | P0 | Knowledge-graph population for the 6 ingested repos: plan first (counts, runtime, verification), then build Neo4j; dump to `C:\EIH_share\` | `feat/graph-population` | Measured node/edge counts; a System-D trace shows `graph.executed=true` with `chunks_injected>0` |
| B5 | P0 | Mode R dataset loaders (RepoBench, CrossCodeEval) in `benchmark/`, after B2 clears them | `feat/benchmark-mode-r-loaders` | Loader tests; slice sizes and seeds recorded |
| **B6** | P0 | EIH-SWE annotation tooling (schema v2, validator, fingerprint) + annotation batches (A annotates too, in `batch_A_*`) | `feat/benchmark-eih-swe-tooling` | Validator passes on every batch |
| **B7** | P1 | Website frontend (`web/`): ask a question, view the trace, citations, provenance badges, mock banner, results page | `feat/web-frontend` | Renders the contract example and a real cached trace; untrusted text shown as plain text |
| B8 | P2 | Tree-sitter chunking (Java, Go, Rust, TS/JS, C/C++) + corpus waves 2–4 (RQ6) | `feat/ingestion-treesitter` | Per-language chunk tests; ingestion counts measured |
| B9 | P1 | EIH-Fresh: post-cutoff tasks from repos outside Tiers 1–5, fingerprinted and frozen (RQ7) | `feat/benchmark-eih-fresh` | Frozen file + fingerprints |
| B10 | P2 | Systems studies on laptop-b: scalability, resilience/fallback, latency decomposition (RQ8) | `feat/experiments-systems-b` (results under `machine_id=laptop-b`) | Measured, laptop-b-tagged results |
| B11 | P1 | Deploy the website (D2) | `feat/web-deploy` | Public URL works; no secrets or paths in responses |

### 4.3 Joint

| ID | Work |
|---|---|
| J1 | EIH-SWE annotation, about 50/50, each into own batch files |
| J2 | Contract changes (both approve) |
| J3 | Paper drafting, continuous from the first real results |
| J4 | Reproducibility package and code freeze (by 15 Nov) |

### 4.4 Hand-offs between laptops

```
A1 escalation fix ──────────────┐
A4 models ─ A5 routing ─ A8 calibrate/freeze ─ A10 Mode Q ─ A11 final test
B4 graph populated ─────────────┘   (D and E are meaningless without it)
B2 licences ─ B5 loaders ─ A9 Mode R
B6 tooling + J1 annotation ─ A10/A11 (task count)
A2 per-attempt objects ─ B3 live mode;  A12 real traces ─ B7 results page / B11 site
```

B never waits on A: until A2 and A12 land, the website runs on mock and cached
traces, always labelled as such.

---

## 5. Timeline to the deadlines

| Week | Laptop A | Laptop B |
|---|---|---|
| **5–11 Oct** | A1, A3, A6, start A4 | Review/merge B1, B2, B3, B4 plan |
| **12–18 Oct** | A4, A5, A2, A8 (validation split only) | B4 build + dump, B6 tooling, B5, annotation |
| **19–25 Oct** | A9, A10 (dev/val), annotation | B7, annotation, B9 start |
| 26 Oct–8 Nov | A11 final test (once), Pareto, ablations | B9, B11 deploy, B8/B10 if time |
| 9–15 Nov | Paper, J4 freeze | Paper, site final, J4 |

**Honest risk statement.** `docs/PROJECT_REPORT.md` §11 sizes the full programme
at about 18 weeks, ending in December. The deadline is 15 Nov. The plan above
puts the core claims (Modes R and Q on EIH-SWE, RQ1–RQ5, RQ8) on the critical
path. Mode P, waves 2–4 and the human study are P2. At the report's own
15–20 min per task, 400 tasks is about 100–133 person-hours of annotation
(DERIVED from §11.1). That is the largest schedule risk after F1.

---

## 6. Decisions needed

| # | Decision | Recommended | Who |
|---|---|---|---|
| D1 | Which **one** machine runs the final A–E comparison | Laptop B has 8 GB vs 6 GB, which is more headroom for 7B-Q4 + BGE + reranker. But A owns `experiments/`. Decide after A4 measures VRAM | A + B |
| D2 | Website hosting | Public site serves **cached real traces** (no GPU needed); live mode only while a laptop runs the backend (demo day) | A + B |
| D3 | What "experiments complete" means for 25 Oct | Mode R + Mode Q dev/val done; final test early November | A + B + supervisor |
| D4 | Large-LLM baseline (`MASTER_DATASET_SPECIFICATION.md` §7.3) | Option (c) 7B with full context, plus (a) cited figures | A |
| D5 | `max_escalation_attempts` 2 → 3 | Decide after A1. At 2, the reranking rung is unreachable | A |
| D6 | Mode P owner (report assumed a Member C) | P2 for B after B9, Defects4J only; otherwise future work | A + B |
| D7 | NVML single-sample energy: MEASURED or ESTIMATED (F3) | ESTIMATED until integrated sampling exists | A |
| D8 | P0-3 calibration model: the audit says gpt-4o-mini, but the locked decision is local-only | Use the local 7B; record the deviation in `RESEARCH_NOTES.md` | A |

---

## 7. GitHub routine (both laptops)

```powershell
# start of every session
git checkout master; git pull
git checkout -b <branch-from-§4>            # or: git checkout <existing-branch>; git merge master
# work, then
python -m pytest -q
git add <specific files>; git commit -m "type(scope): summary"
git push -u origin <branch>
gh pr create --base master --fill            # or open the PR on github.com
# review the other laptop's PRs: gh pr list ; gh pr checkout <n> ; python -m pytest -q
```

Never push to `master`, never force-push, never commit `.env`, data or model
weights. Merge only after the other laptop approves. Update your PROGRESS file
at the end of each session.
