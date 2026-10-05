# EIH Work Plan — one laptop, the original plan, nothing missed

**Single source of truth for what is done and what comes next.**
Last updated: 2026-10-05 (late night). Since this date the **whole project is built on one
laptop (laptop-a) by Avaneesh**; there is no second laptop and no task split (change C11).

## 0. Where the plan comes from (read first)

The **original plan** is fixed and is not changed by this file. It is frozen word for word in
**`docs/original_plan.md`** (the Major Project Report of 25/26 Aug 2026), with:

- `docs/PROJECT_REPORT.md` §3 (research questions RQ1–RQ8), §7 (five systems A–E, three
  test modes R/Q/P), §11 (phases 0–12)
- `docs/MASTER_DATASET_SPECIFICATION.md` §1 **locked decisions** (all six dataset tiers
  executed, local models only, **EIH-SWE 400–500 human-verified tasks**, top SE journal),
  §4 dataset registry, §8 order of work, §9 which dataset answers which RQ

These two documents have only received status updates since 2026-10-03; their research
content is unchanged. This file lists the work in order and tracks status. **Any deviation
from the original plan is in §5 (change register), with date and who decided.** If it is not
in §5, it has not changed. Nothing is dropped without Avaneesh's decision.

## 1. Plain words (glossary)

| Term | Meaning |
|---|---|
| **RAG** | Retrieval-Augmented Generation — the core of this project: first **retrieve** the relevant code/docs from the indexed repositories (dense vectors, BM25, hybrid, cross-encoder reranking, knowledge graph), then **generate** a grounded, cited answer from that evidence |
| **System A–E** | The five-system RAG ablation ladder, each adding one capability: **A** LLM only, no retrieval · **B** + fixed hybrid RAG (dense + BM25, fixed top-k) · **C** + task classification and adaptive retrieval · **D** + knowledge-graph augmentation · **E** + quality gate and bounded escalation (the full system). **E + routing** adds task-aware model routing (RQ4) |
| **Mode R** | Retrieval test: did retrieval find the right files/spans? (Recall@K, Precision@K, MRR, NDCG; no generation, cheap) |
| **Mode Q** | Question-answer test: is the answer correct and does it cite the right code? |
| **Mode P** | Patch test: the AI writes a code fix and the project's own tests check it |
| **EIH-SWE** | Our own benchmark of 400–500 human-checked engineering questions (main contribution) |
| **EIH-Fresh** | ~150 brand-new questions for the final, memorisation-free test |
| **Calibration (P0-3)** | Tuning on the 12 practice ("validation") questions, then freezing every setting |
| **Held-out test** | The 24 questions nobody looks at until the very end; run once |
| **Manifest** | The frozen record of every setting, with a fingerprint (hash) |

## 2. Deadlines

| Date | Deliverable |
|---|---|
| **25 Oct 2026** | Major implementation complete, experiments complete |
| **15 Nov 2026** | Final paper, final code, final results, reproducibility docs |

**Honest risk (not a plan change):** `PROJECT_REPORT.md` §11 sized the programme at ~18 weeks
for three people; it is now one person on one laptop. All of it does not fit 25 Oct. What
"experiments complete" means on 25 Oct is decision **D3** (§4); until it is decided, nothing
is cut.

## 3. The work, in order (original phase numbers in brackets)

Status: ✅ done · 🟡 started · ⬜ not started. Each step is one branch and one PR.

| Step | Work | Original | Status 2026-10-05 |
|---|---|---|---|
| 1 | RAG corpus: ingest + index (Qdrant vectors, BM25) the 6 wave-1 repositories (Flask, FastAPI, Requests, Pytest, Sphinx, Pylint) | Phase 0 | ✅ 48,046 chunks |
| 2 | Local LLMs 1.5B / 3B / 7B installed, measured, routing wired; job queue; single config `configs/inference.yaml` | Phase 1 | ✅ PRs #4, #8, #10 + audit |
| 3 | Measurement and validity fixes from the restore-original-plan audit (§5 C6–C7, C12–C18) | P0 audit | ✅ branches `feat/m5-live-calibration`, `restore-original-plan` (PRs to merge) |
| 4 | **Fix oversized chunks**: 3,485 of 48,046 chunks exceeded BGE's 512-token window (wrong tokenizer, long functions/paragraphs/lines never split, code between definitions dropped, wrong sub-chunk line ranges). Fixed; re-ingested into `eih_knowledge_v2` (53,905 chunks, 0 over 512, every line covered); retrieved chunks now carry line ranges into the prompt and citation check | Phase 0 | ✅ branch `fix/ingestion-chunk-size` |
| 5 | **Build our own knowledge-graph builder** and the graph for the 6 repositories (reachable by the graph retriever; expansion not via the Repository hub node) | Phase 3 | ⬜ |
| 6 | Finish answer locations (retrieval labels) for all 60 questions; fix or exclude ops-052 / ops-053; human check of the drafts; blind protocol for the 24 test questions | Phase 4 | 🟡 36 drafted |
| 7 | **Calibration** on the 12 practice questions with the live 7B; freeze the manifest | P0-3 | ⬜ |
| 8 | Mode R on our questions: **implement** Recall@K, Precision@K, MRR, NDCG@K (not built yet — plan §9.2) and run them; re-measure reranker energy in batches | Phase 5 | ⬜ |
| 9 | Mode Q: Systems A–E on the dev + practice questions | Phase 6 | ⬜ (job queue ready; A/B/C smoke-verified) |
| 10 | System E + routing (1.5B→3B→7B) vs E for RQ4 | Phase 1 / RQ4 | 🟡 system implemented (`system_e_routed`), not yet run |
| 11 | **EIH-SWE annotation tool** (schema v2, validator, SHA-256 task fingerprint — plan §8.2; not built yet) and **annotation to 400–500 questions** — continuous from now on | Phase 4 | 🟡 60 exist |
| 12 | **Licence audit** of every external dataset (blocking for downloads) | spec §4.1 | ⬜ |
| 13 | External Mode R: RepoBench, CrossCodeEval | Phase 5 | ⬜ |
| 14 | External Mode Q: CodeRepoQA (1,000 stratified), StackRepoQA (1,318) | Phase 6 | ⬜ |
| 15 | Large-AI-model baseline (spec §7.3, decision D4) | spec §7.3 | ⬜ data from the long-context probe exists |
| 16 | Code splitting (tree-sitter) for Java, Go, Rust, JS/TS, C/C++ | Phase 2 | ⬜ |
| 17 | More projects: corpus waves 2–4 (≥ 8 repos, ≥ 4 languages) + their code map | Phase 3 | ⬜ |
| 18 | Security-risk slice: Big-Vul / PrimeVul (500 each, classification, RQ4) | spec §8 phase 6 | ⬜ |
| 19 | Mode P patch harness incl. the **agentic** routing tier of Fig. 6.1 (not built yet): Defects4J → BugsInPy, CodeFlaws → SWE-bench Lite, SWE-bench Pro (731), SWE-rebench (~500) → Multi-SWE-bench flash (300), SWE-bench Multilingual (300) | Phase 7 | ⬜ (D6) |
| 20 | Systems studies: scalability 10K→500K chunks, resilience / fallback, latency breakdown | Phase 8 | ⬜ |
| 21 | Build EIH-Fresh (~150 post-cutoff questions, fingerprinted, frozen) and run it once | Phase 9 | ⬜ |
| 22 | Final held-out test, once, N = 5; Pareto frontier; ablation deltas Δ(A→B)…Δ(D→E); CO₂e per successful task | Phase 10 | ⬜ |
| 23 | Optional human study (8–12 participants) if ethics approval is obtained | Phase 11 | ⬜ optional |
| 24 | Project website: overview, live demo, results dashboard (API contract v1 done) | added (C8) | 🟡 |
| 25 | Paper, written alongside from the first real results; reproducibility package | Phase 12 | ⬜ |

Supporting corpora (spec §4): CommitBench (reference for our own commit layer), LogHub (log
analysis), SWE-bench Multimodal (diagram track) — used as the spec describes, not as benchmarks.

## 4. Open decisions (Avaneesh, with the supervisor where noted)

| # | Decision | Recommendation |
|---|---|---|
| D3 | What "experiments complete" means on 25 Oct (supervisor) | Steps 4–10 by 25 Oct; the rest with fixed November dates |
| D4 | Large-AI-model baseline (spec §7.3) | The 7B at the largest context that fits (16K measured) + cited published figures |
| D6 | Mode P scope (one person now) | Defects4J first; the rest in the order of step 19 as time allows |
| D9 | This laptop's Qdrant is v1.13.2; `docker-compose.yml` pins v1.15.1 | Snapshot, then upgrade (needs OK: recreates the container) |
| D10 | Delete old merged / unused branches | After this plan is merged (needs OK) |
| D12 | Blind labelling of the 24 test questions (one person can't be blind to their own system) | Label them before the systems are tuned, freeze the labels, record the date |
| D13 | The original documents disagree with each other: EIH-SWE "~300–450 tasks" (report §11) vs "400–500" (spec §1, locked); "28 repositories" (report §8.1) vs 26 in `datasets/registry.yaml` since it was first committed; "21 task types" (report §6.2) vs 22 + `unknown` in the code since the first commit | Treat the spec's locked 400–500 as binding; correct the two counts in the paper text |
| D14 | Quality metric "completeness" (plan §9.2) has no evaluator yet (evidence coverage is the closest) | Add a completeness evaluator, or define coverage as completeness in the paper |
| D15 | Citations [9] and [10] could not be found; [2]'s DOI is unconfirmed (`docs/CITATION_AUDIT.md`) | Supply the exact citations or remove them before submission |
| D16 | System C's answer to dev task 010 differed between two runs (778 vs 292 tokens) at temperature 0, seed 42 | Calibration (3 trials per task) measures run-to-run variance before any claim |

## 5. Change register — every deviation from the original plan

| # | Date | Change | Decided by | Why |
|---|---|---|---|---|
| C1 | 2026-10-03 | Team smaller than the 3–4 members the plan assumed | fact | see C11 |
| C2 | 2026-10-05 | Systems A–E use one fixed model, `qwen2.5-coder:7b`, all layers on the GPU; routing 1.5B→3B→7B is evaluated as an extra system (RQ4 unchanged) | Avaneesh | A–E then differ only in search/checking |
| C3 | 2026-10-05 | Retry (escalation) steps 2 → 3 (spec open decision 5) | Avaneesh | At 2 the strongest retry step was unreachable |
| C4 | 2026-10-05 | Context 12,288 tokens; thermal rule 90 °C → cool to 65 °C, repeat. The output limit was set to 1,024, then **restored to the plan's 2,048** (C17) | Avaneesh / evidence | Measured: largest prompts ~9K; 7B fits at 12K, slows 5–7× from 20K |
| C5 | 2026-10-05 | CO₂e uses India's grid (713 gCO₂e/kWh), not the UK default (233) | `.env` | The laptop is in India; the UK value was a stale default |
| C6 | 2026-10-05 | Manifest built from the real settings (hash `aa733133d041f11c` → `bc6c83d062f075d9`) | fix | The old manifest (gpt-4o-mini, temp 0.1, 2 repos) was never what ran |
| C7 | 2026-10-05 | System A gets a "no project files" prompt | fix | With the evidence-only prompt A refused every question |
| C8 | 2026-10-05 | Project website added | Avaneesh | Addition; nothing removed |
| C9 | 2026-10-05 | The first version of this file had dropped original items (400–500 questions, licence audit, external datasets, EIH-Fresh, systems studies) | — | **Reverted** — all restored above |
| C10 | 2026-10-05 | Calibration uses the local 7B, not gpt-4o-mini as the M5 audit wrote | locked decision | Spec §1 (local only) overrides the audit |
| C11 | 2026-10-05 | **One person, one laptop (laptop-a).** All former laptop-b work is in §3. Work laptop-b already merged is kept (escalation fix, 36 retrieval labels, API contract v1, Qdrant healthcheck). Laptop-b's unmerged graph builder is **not** used; we build our own (step 5) | Avaneesh | Avoid drift and miscommunication between two laptops |
| C12 | 2026-10-05 | One config file `configs/inference.yaml` for Systems A–E and all routing tiers; removed the unused `configs/default.yaml` (stale UK/OpenAI values) and paid-API models from `configs/models.yaml` | audit | Single source of truth; locked local-only decision |
| C13 | 2026-10-05 | Systems C–E run the **real** task classifier (they had been given the benchmark's answer-key labels and threshold since 2026-08-20) | audit (fix) | Plan C1/§6.2: classification is automatically inferred |
| C14 | 2026-10-05 | Measurement tiers exactly as plan §9.1 (CO₂e and cost ESTIMATED, not DERIVED); CPU energy restored as ESTIMATED (TDP × CPU utilisation × time) | audit (fix) | Plan §9.1, §12 |
| C15 | 2026-10-05 | Plan §9.2 latency decomposition recorded per trial (T_query, T_retrieval, T_rerank, T_context, T_generation) | audit (restore) | It was missing |
| C16 | 2026-10-05 | `system_e_routed` (E + task-aware model routing) added for RQ4 | audit (restore) | Plan C1 / Fig. 6.1 routing; no experiment could run RQ4 |
| C17 | 2026-10-05 | Output limit back to the plan's 2,048 tokens; untimed warm-up before trials | evidence | 1,024 cut off a real answer; one-time loading leaked 16–18 s into a measured trial (plan §10.4) |
| C18 | 2026-10-05 | README title and research questions restored to the original (they had become "Task-Aware Energy-Efficient RAG" and a generic research question); two-laptop tooling removed/archived | audit (restore) | Original plan |

## 6. Routine

- **Start of every session** (Claude does it): `git fetch`, sync the branch with `master`,
  read `PROGRESS-A.md`, say what was done last and what is next in §3.
- **End of every session**: tests → `PROGRESS-A.md` entry → commit on the feature branch →
  push (GitHub = private backup) → Avaneesh merges the PR on GitHub.
- Never push to `master`, never force-push, never delete anything without asking.
- **One plan:** changes go into this file; deviations into §5.

Repository (private backup): https://github.com/kanhaiya27/engineering-intelligence-hub
