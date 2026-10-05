# EIH Work Plan — who does what, and when

**Single source of truth for task assignment between the two laptops.**
Last updated: 2026-10-05 night (Laptop A), after a full audit against the original plan.
Update the status column whenever a task's PR merges.

## 0. Where the plan comes from (read first)

The **original plan** is fixed and is not changed by this file:

- `docs/PROJECT_REPORT.md` §3 (RQ1–RQ8), §7 (five-system ladder A–E, three evaluation
  modes R/Q/P), §11 (phases 0–12)
- `docs/MASTER_DATASET_SPECIFICATION.md` §1 **locked decisions** (all six dataset tiers
  executed, local models only, **EIH-SWE 400–500 human-verified tasks**, top SE journal),
  §8 sequencing by mode, §9 RQ → dataset matrix

This file only assigns that plan to the two laptops and tracks status. **Any deviation
from the original plan is listed in §7 (change register) with date, who decided, and why.**
If something is not in §7, it has not changed.

This file replaces `docs/PROJECT_PLAN.md` from laptop-b's old branch `docs/project-plan`
(written in parallel on 2026-10-05, 01:36). Every item of that file is carried over here;
§8 maps its IDs to these.

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
| **25 Oct 2026** | Major implementation complete, experiments complete |
| **15 Nov 2026** | Final paper, final code, final results, reproducibility docs |

**Honest risk (not a plan change):** `PROJECT_REPORT.md` §11 sizes the full programme at
~18 weeks ending in December, and the locked decisions include 400–500 annotated tasks and
external datasets in all six tiers. That does not fit 25 Oct. What "experiments complete"
means on 25 Oct is open decision **D3** (§6) — until it is decided, nothing is cut.

## 3. Phase status (original phase numbers, `PROJECT_REPORT.md` §11)

| Phase | Work (original) | Owner | Status 2026-10-05 |
|---|---|---|---|
| 0 | Foundation, corpus ingestion, retrieval verified | A + B | ✅ Done (wave 1: 6 repos, 48,046 chunks) |
| 1 | Local inference stack (Ollama + Qwen2.5-Coder 1.5B/3B/7B), wire routing | A | ✅ Done (A1, A2; PRs #4, #8, #10) |
| 2 | Tree-sitter chunking for Java, Go, Rust, TS/JS, C/C++ (RQ6) | B | ⬜ B11 |
| 3 | Corpus waves 2–4; knowledge-graph population | B | 🟡 Graph for wave 1 built (B3, draft PR); waves 2–4 ⬜ B12 |
| 4 | **EIH-SWE annotation, 400–500 tasks** (locked) | A + B | 🟡 60 tasks exist; B1 labels drafted for 36; batches ⬜ B4/J1 |
| 5 | **Mode R**: RepoBench, CrossCodeEval (+ EIH labels) | A | ⬜ A4 (EIH labels), A7 (external; needs B8, B9) |
| 6 | **Mode Q**: EIH-SWE, CodeRepoQA, StackRepoQA — Systems A–E | A | ⬜ A5 (EIH-SWE), A8 (external) |
| 7 | **Mode P**: patch harness (Defects4J → SWE-bench Pro → Multi-SWE-bench) | Member C (none) | ⬜ Unassigned — decision D6 |
| 8 | Systems studies: scalability, resilience, latency decomposition | B | ⬜ B13 |
| 9 | EIH-Fresh construction, fingerprinting, freeze (RQ7) | B | ⬜ B14 (run: A12) |
| 10 | Final held-out evaluation (N=5), Pareto frontier, ablation deltas | A | ⬜ A5 (test once) + A6 |
| 11 | Optional human study (ethics approval) | B | ⬜ B15 (optional) |
| 12 | Paper drafting, continuous | All | ⬜ B5 + J3 |
| — | P0-3 calibration on the validation split with live local models; re-freeze manifest | A | 🟡 A3 (integrity fixes done, run pending) |
| — | Project website (overview, live demo, results) | B | 🟡 API contract v1 merged (PR #13); B6 |

**Rule: only Laptop A produces headline measured results** (see decision D1).
Laptop B runs are for development, smoke tests and the systems studies (B13), written
under `experiments/results/**/machine_B/`, and never mixed into a comparison table.

## 4. Task queues

Each task is one branch and one PR into `master`. IDs A1–A6 and B1–B6 are unchanged from
the first version of this file; A7+ and B7+ are original-plan items that were missing here.

### Laptop A (Avaneesh, RTX 4050) — owns `routing/` `generation/` `verification/` `experiments/` `retrieval/` `sustainability/`

| # | Branch | Task | Needs | Target | Status |
|---|---|---|---|---|---|
| A1 | `feat/local-inference` | Phase 1a: `.env` fix, NVML meter, provenance, VRAM study | — | 5 Oct | ✅ PR #4 |
| A2 | `feat/local-inference-routing` (+ `feat/gpu-job-queue`) | Phase 1b: 7B decision, `OllamaProvider`, routing wired, escalation 2→3, long-context probe, job queue | — | 11 Oct | ✅ PRs #8, #10 |
| A3 | `feat/m5-live-calibration` | Measurement-integrity fixes (done: runner, energy labels, System A prompt, manifest from runtime, graph wiring for D/E); P0-3 calibration on the 12 val tasks with live models; re-freeze manifest | B1 (ops-052/053), B7 (chunks) | 14 Oct | 🟡 fixes done, run pending |
| A4 | `feat/mode-r-retrieval-eval` | Mode R on EIH tasks with B1 labels (Recall@K, MRR, nDCG); re-measure reranker energy in batches (report §10.4) | B1 verified | 16 Oct | ⬜ |
| A5 | `feat/mode-q-systems-a-e` | Mode Q: Systems A–E on dev + val; held-out test once, N=5, via the job queue | B3 merged + dump restored on A, B7 | 23 Oct | ⬜ |
| A6 | `feat/pareto-ablation-results` | Pareto frontier, ablation deltas Δ(A→B)…Δ(D→E), CO₂e per successful task | A5 | 25 Oct | ⬜ |
| A7 | `feat/mode-r-external` | Mode R external: RepoBench, CrossCodeEval (+ CodeRepoQA/StackRepoQA retrieval slices) | B8, B9 | D3 | ⬜ |
| A8 | `feat/mode-q-external` | Mode Q external: CodeRepoQA, StackRepoQA slices, Systems A–E | B8, B9 | D3 | ⬜ |
| A9 | `feat/large-llm-baseline` | Large-LLM baseline (spec §7.3, decision D4); long-context probe data exists (12K fits, 16K full, 20K+ spills) | D4 | D3 | ⬜ |
| A10 | `feat/generation-attempt-trace` | Per-attempt trace objects for the website's live mode; export real traces from A5 runs for the cached mode | API contract v1 | 24 Oct | ⬜ |
| A11 | `feat/criticality-slice` | Big-Vul / PrimeVul criticality slice (RQ4 secondary, spec §8 phase 6) | B8, B9 | D3 | ⬜ |
| A12 | `feat/eih-fresh-run` | EIH-Fresh single frozen run (RQ7) | B14 | Nov | ⬜ |
| A13 | `benchmark/data/eih_swe/batch_A_*` | Annotate A's half of EIH-SWE (J1) | B4 tooling | continuous | ⬜ |

### Laptop B (Sanvi, RTX 5050) — owns `ingestion/` `knowledge/graph/` `benchmark/` `apps/` `web/` `docs/`

| # | Branch | Task | Needs | Target | Status |
|---|---|---|---|---|---|
| B1 | `feat/benchmark-retrieval-labels` | Retrieval ground truth for the 60 tasks. Done: 36 dev+val drafted. Left: human verification of 35 drafts; fix or exclude **ops-052, ops-053** (val); blind protocol for the 24 test tasks (agree with A) | — | 10 Oct | 🟡 PRs #7, #9 |
| B2 | `fix/compose-qdrant-healthcheck` | Qdrant healthcheck | — | 7 Oct | ✅ PR #5 |
| B3 | `feat/graph-populate-wave1` | Populate Neo4j for the 6 wave-1 repos; dump to `C:\EIH_share\neo4j.dump`. **Before merge: F6** (graph expansion goes through the `Repository` hub node → mostly arbitrary sibling files; exclude `:Repository` from expansion paths in `knowledge/graph/neo4j.py`) | — | 16 Oct | 🟡 draft PR |
| B4 | `feat/benchmark-eih-swe-batch1` (then `-batchN`) | EIH-SWE annotation tooling (schema v2, validator, fingerprints) + batches toward **400–500 tasks** (locked); B's half in `batch_B_*` | — | batch 1: 20 Oct | ⬜ |
| B5 | `docs/report-real-results` | Put A's measured results into `docs/PROJECT_REPORT.md` and the paper | A5/A6 | 25 Oct → 15 Nov | ⬜ |
| B6 | `feat/web-project-site` | Website in `web/` served by FastAPI: overview, live demo (classification, retrieval, model tier, gate verdict, measured energy), results dashboard from `experiments/results/**/machine_A/*.json`; backend hardening (CORS, rate/input limits, request IDs, PII-free logs); deploy (D2) | API contract v1 ✅ | skeleton 24 Oct, done 10 Nov | 🟡 contract merged (PR #13) |
| B7 | `fix/ingestion-chunk-size` | **Oversized chunks** (found 2026-10-05): 81 chunks > 2,048 tokens, largest 67,021 (lockfiles, contributor/sponsor lists, `plugin_list.rst`). Cap chunks at ~512 tokens (BGE-small embeds only the first 512) and skip lockfiles / generated data; re-ingest; new snapshot + SHA256 in `C:\EIH_share\`; re-check B1 labels against the new chunks | — | **before A3, 12 Oct** | ⬜ |
| B8 | `docs/licence-audit` | Licence audit of every external dataset from official sources (spec §4.1, **BLOCKING** for downloads) | — | 14 Oct | ⬜ |
| B9 | `feat/benchmark-external-loaders` | Loaders + evaluation slices (seeded) for RepoBench, CrossCodeEval, CodeRepoQA, StackRepoQA, Big-Vul/PrimeVul | B8 | D3 | ⬜ |
| B10 | `fix/api-graph-store` | Live demo/API builds `AdaptiveRetrievalPipeline(graph_store=None)` (`apps/api/routers/adaptive.py`): System D in the demo has no graph. Pass the Neo4j store | B3 | 16 Oct | ⬜ |
| B11 | `feat/ingestion-treesitter` | Tree-sitter chunking for Java, Go, Rust, TS/JS, C/C++ (RQ6, phase 2) | — | after 25 Oct | ⬜ |
| B12 | `feat/corpus-waves-2-4` | Corpus waves 2–4 (≥ 8 repos, ≥ 4 languages) + their graph (phase 3) | B11 | Nov | ⬜ |
| B13 | `feat/experiments-systems-b` | Systems studies on laptop-b: scalability (10K→500K chunks), resilience/fallback, latency decomposition (RQ8, phase 8); results under `machine_B` | — | Nov | ⬜ |
| B14 | `feat/benchmark-eih-fresh` | EIH-Fresh: post-cutoff tasks from repos outside tiers 1–5, fingerprinted and frozen (RQ7, phase 9) | B4 tooling | Nov | ⬜ |
| B15 | — | Optional human study (8–12 participants) if ethics approval is obtained (phase 11) | approval | Nov | ⬜ optional |

### Joint

| # | Work |
|---|---|
| J1 | EIH-SWE annotation, about 50/50, each into own batch files (`batch_A_*`, `batch_B_*`) |
| J2 | API contract changes (`apps/api/contract/`) need both laptops' approval |
| J3 | Paper drafting, continuous from the first real results |
| J4 | Reproducibility package and code freeze (by 15 Nov) |

### Dependencies between the queues

- **A3 needs B7** (re-chunked corpus) **and B1's ops-052/053 fix** — calibration must run on
  the corpus and tasks the final runs use.
- **A4 needs B1 verified**. **A5 needs B3 merged + `neo4j.dump` restored on Laptop A**: the job
  queue now refuses D/E runs until the graph has all 6 repositories (graph preflight).
- **A7/A8/A11 need B8 then B9.** **A12 needs B14.** **B5 needs A5/A6.**
- **B6 (website) reads A's result JSON.** Every result file has top-level `study`,
  `provenance` and `results`; A announces any shape change in PROGRESS-A before merging.

## 5. Collision rules

1. **Stay in your own directories.** Editing the other laptop's directory requires their
   review on the PR.
2. **Shared files** — `core/`, `configs/`, `knowledge/schemas/`, `knowledge/vector/`,
   `evaluation/`, `tests/conftest.py`, `requirements*.txt`, `docker-compose.yml`,
   `.env.example`, `pyproject.toml`, `.claude/`, root docs: write a line in your PROGRESS
   file *before* starting, keep the change small, tag the commit `[must-pull]`, and get the
   other laptop's review.
3. **Each laptop has its own results folder**: `experiments/results/<study>/machine_A/` or
   `machine_B/`. Never write into the other's.
4. **`docs/` belongs to B**, except `docs/WORK_PLAN.md`, which both update by PR.
5. **Small PRs, merged often.** `git pull` on `master` before every new branch.
6. **Never** push to `master`, force-push, rewrite pushed history, or delete without asking.
7. **One plan.** Plan changes go into this file (and §7 if they deviate from the original
   plan) — never into a second plan file.

## 6. Open decisions (owner: Avaneesh as project manager, with the supervisor where noted)

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Which machine runs the final A–E comparison | Laptop A: Phase 1 is measured there, the 7B fits fully at 12K, digests pinned. Moving to B means repeating Phase 1 on B | A5 |
| D2 | Website hosting | Public site serves cached real traces; live mode only while a laptop runs the backend | B6 |
| D3 | What "experiments complete" means on 25 Oct (supervisor) | Mode R + Mode Q on EIH-SWE dev/val done by 25 Oct; held-out test, external datasets and remaining annotation scheduled into Nov with dates | everything marked "D3" |
| D4 | Large-LLM baseline (spec §7.3) | (c) the 7B at the largest context that fits (16K measured), plus (a) cited figures | A9 |
| D6 | Mode P owner (report assumed a Member C) | Defects4J only, by B after B14, otherwise future work | phase 7 |
| D9 | Laptop A's Qdrant is v1.13.2; `docker-compose.yml` and laptop B use v1.15.1 | Snapshot, then upgrade A to 1.15.1 (needs OK: recreates the container) | reproducibility |
| D10 | Delete merged / superseded branches (incl. `docs/project-plan`, `phase-*`) | Yes, after this audit is merged (needs OK) | tidiness only |
| D12 | Blind labelling protocol for the 24 test tasks | Labeller who never runs the systems; labels frozen before the test run | A5 test run |

## 7. Change register — every deviation from the original plan

| # | Date | Change | Decided by | Why |
|---|---|---|---|---|
| C1 | 2026-10-03 | Team is 2 people, not 3 (§11 assumed Members A, B, C) → Mode P (phase 7) has no owner | fact | D6 |
| C2 | 2026-10-05 | Systems A–E use one fixed model, `qwen2.5-coder:7b`, all layers on GPU; routing 1.5B→3B→7B is evaluated as an additional system (RQ4 unchanged) | Avaneesh | Keeps A–E differing only in retrieval/verification |
| C3 | 2026-10-05 | `max_escalation_attempts` 2 → 3 (spec open decision 5) | Avaneesh | At 2 the reranking rung was unreachable |
| C4 | 2026-10-05 | num_ctx 12,288, output limit 1,024 tokens (was 4,096 / 2,048); thermal rule 90 °C → cool to 65 °C, repeat | Avaneesh | Measured: largest prompts p99 ~9K; 7B fits at 12K, spills from 20K |
| C5 | 2026-10-05 | CO₂e uses India's grid (713 gCO₂e/kWh) instead of the UK default (233) | `.env` (laptop in Dehradun) | The UK value was a stale default; manifest now records the real one |
| C6 | 2026-10-05 | Manifest built from the runtime settings (hash `aa733133d041f11c` → `bc6c83d062f075d9`); job queue refuses a mismatch | fix | The old manifest (gpt-4o-mini, temp 0.1, 2 repos) was never what ran |
| C7 | 2026-10-05 | System A gets a no-retrieval prompt | fix | With the evidence-only prompt A refused every task (strawman) |
| C8 | 2026-10-05 | Project website added as deliverable B6 | Avaneesh | Addition; nothing removed |
| C9 | 2026-10-05 | First version of this file listed only "60-task benchmark" and Mode R on EIH labels for 25 Oct, and lacked the licence audit, external loaders, EIH-Fresh, systems studies, criticality slice | — | **Reverted**: restored as A7–A13, B7–B15; scope for 25 Oct is decision D3 |
| C10 | 2026-10-05 | P0-3 calibration uses the local 7B, not gpt-4o-mini as the M5 audit wrote | locked decision (local only) | Spec §1 overrides the audit |

## 8. Mapping from laptop-b's `docs/PROJECT_PLAN.md` (superseded)

| PROJECT_PLAN | Here | | PROJECT_PLAN | Here |
|---|---|---|---|---|
| A1 F1 escalation fix | done by B (PR #11) | | B1 API contract | ✅ PR #13 |
| A2 per-attempt objects | A10 | | B2 licence audit | B8 |
| A3 F2–F5 energy provenance | ✅ in A3 | | B3 web backend | B6 |
| A4 Ollama ladder | ✅ A1/A2 | | B4 graph population | B3 |
| A5 routing wired | ✅ A2 | | B5 Mode R loaders | B9 |
| A6 machine_id | ✅ A1 | | B6 annotation tooling | B4 |
| A7 escalation 2→3 | ✅ A2 | | B7 frontend | B6 |
| A8 P0-3 calibration | A3 | | B8 tree-sitter + waves | B11, B12 |
| A9 Mode R | A4, A7 | | B9 EIH-Fresh | B14 |
| A10 Mode Q dev/val | A5, A8 | | B10 systems studies | B13 |
| A11 final test | A5 + A6 | | B11 deploy | B6 |
| A12 real traces | A10 | | D1–D8 | §6 / §7 |
| A13 large-LLM baseline | A9 | | J1–J4 | J1–J4 |

## 9. How the two laptops work together (no work is lost)

**Both laptops work at the same time, on different directories.** There is no "your turn /
my turn". Work only moves between laptops through GitHub: a branch → PR → merge into `master`.

- **"Pull first"** means: the other laptop merged something into `master` that yours does not
  have yet. If that change is tagged `[must-pull]` (shared files), the guard blocks edits until
  you pull, so you never build on an outdated shared file. Pulling never deletes your work.
- **Start of every session** (Claude does it): `git fetch`; on a feature branch
  `git merge origin/master`; on `master` `git pull`; then read both PROGRESS files.
- **End of every session** (Claude does it): tests → PROGRESS entry → commit on the feature
  branch → push the feature branch. Laptop A has standing permission to push its feature
  branches without asking.
- **After a PR is merged**, tell the other person "merged <branch>" (+ "MUST PULL" if tagged).
- **Never keep work only on one laptop overnight**: push the feature branch (a draft PR is fine).
- An **old branch that conflicts with `master`** (like `docs/project-plan`) is not merged:
  its useful content is moved into a fresh branch from `master`, and the old branch is deleted
  only after the owner says so.

Manual equivalent:
```powershell
git checkout master; git pull                 # start
git checkout -b <branch-from-the-table>
python -m pytest                              # before every push
git push -u origin <branch>                   # then open the PR on GitHub
```

Repository: https://github.com/kanhaiya27/engineering-intelligence-hub (private).
