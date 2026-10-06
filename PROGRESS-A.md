# PROGRESS — Laptop A (Avaneesh · RTX 4050 6 GB)

`machine_id: laptop-a` · Owns: `routing/` `generation/` `verification/`
`experiments/` `retrieval/` `sustainability/`

Newest entries on top. One entry per working session: what changed, what was
measured (with numbers only if actually measured), what is blocked.

---

## 2026-10-06 (later) — Step 3: drafting tool, review queue, M1 rating batch, power check

Decisions recorded (ASK_ME Decided; WORK_PLAN C27–C29).

**3a: drafting tool** (`benchmark/drafting.py`, `scripts/draft_tasks.py`)
- Seeded span sampling; drafts FAIL on missing or out-of-file lines; batches with a rotating requester.
- 40/20/40 split assigned at first approval (a test slot needs a second reviewer).
- Fingerprints; `lock_sets`.
- Round 1: 70 drafts (6 repos × 6 stages, every claim checked in code, 0 validation failures; 2 spans
  skipped with reasons). Two drafts expose real pinned-code defects: Requests `multiple_domains`, and
  Pylint `visit_try` missing `no-else-raise`.

**3b / 3c: queue by priority**
- calibration (10);
- L1 labels (36);
- audit-fix proposals (20; requester excluded);
- test correctness (24 × 2, rotating pairs);
- drafts (70);
- M1 blind rating batch: 40 answers, 2 raters each, key outside git, protocol pre-registered
  (`docs/M1_PROTOCOL.md`) before any rating.

**3d: power check.** Binary per-stage tests are not detectable at any reachable size; RQ4 energy saving
below MDE. Routing tier from the classifier = from labels on 16/24 dev, 6/12 val.

**3e:** lock dry run (empty: nothing approved yet); the lock covers the pilot files.

**Fixes found on the way:** reviewer CLI forced to UTF-8 (Windows), GPU-hours field in the daily report.

**Review counts today:** 0 decisions (queue just opened). GPU used: 3.7 h (2c run).

**Next** — Step 4 after "go"; drafting rounds continue daily; the M1 selection runs once ratings are in.

---

## 2026-10-06 — Step 2: preflight, approved decisions, confounds on dev/val, freeze

Branch `master-fix`, fast-forwarded to master `58bf4ab` (PR #18).

**Preflight** — clean.
- Graph = build record + exactly the 2 test nodes and 1 edge.
- Working tree: only `docs/SRS.pdf` (untracked).
- Benchmark files unchanged since v1.1; only test IDs were read.

**Approved decisions applied**
- A3: graph backed up (`C:/EIH_backups/…`), 2 nodes and 1 edge deleted; the graph equals its build
  record; the test suite leaves it unchanged.
- A1 / C23: D = C + graph on every task.
- A2 / C24: success = correct AND cites labelled evidence.
- D12: 24 test tasks queued (4 batches, rotating pairs). Found by task ID only: 4 have evidence that
  cannot be shown.
- Found: results JSON was git-ignored, so the 5 Oct Mode R/energy JSON was never committed. Now versioned.

**Step 2**
- 2a / C25: classifier rules from dev only. All four fields right: dev 3 → 12 of 24, val 1 → 2 of 12.
- 2b / C26: fused-only cut-off at 0.25; zero-evidence tasks 0 for every system.
- 2c: probes. Variation comes from the cache/load state and `num_predict` (V1). 3-trial run: 648 units,
  all ok.
- 2d: `docs/BENCHMARK_AUDIT.md`. 7 of the 20 tasks not yet corrected have answer or question problems;
  11 of 36 overall.
- 2e: `docs/FROZEN_CONFIG.md`, manifest `95e5a587c9d60e7a`. The limit is not raised (T1).

**Key measured results (dev/val, descriptive)**
- Token F1 0.235–0.260 for all systems; 0/648 trials at the threshold (M1).
- E refuses 21% with the same unsupported rate as D.

**Next** — Step 3 after "go"; decisions M1, T1, V1 first.

---

## 2026-10-05 (late) — Master prompt Steps 0 + 1: schedule, review queue, measurement validity

Branch `master-fix` (tag `pre-master-fix` = master 68a072d before it).

**Step 0**
- `docs/SCHEDULE.md`: day by day to 20 Oct; GPU budget ≈ 550 GPU-h for Modes R/Q vs ≈ 300
  available, plus Mode P; review need ≈ 135 h vs 84 h. Options are in `ASK_ME.md` (G1, R1).
- Review queue (`benchmark/review.py`, `scripts/review.py`, `docs/REVIEW_GUIDE.md`).
  `calibration-01` (10 dev/val tasks) queued for all four reviewers.
- Found: 9 dev/val tasks cite a doc file with no line numbers (ASK_ME L3).

**Step 1**
- 1a: Mode R metrics plus a run on the 36 dev/val labels (provisional, draft labels). D = C on 33/36
  tasks: the policy picks a graph strategy for only 3 (ASK_ME A1). C/D retrieve nothing on 3 tasks.
- 1b: CO₂e per successful task, including model loads.
- 1c: statistics (`experiments/stats.py`).
- 1d: no invented scores. The 0.50 fills and an unexplained ×1.5 on correctness are removed (C19).
- 1e/1f: citation-span outcome independent of E's gate (C22); blind human-rating subset tools.
- 1g: the manifest binds configs, data files, the collection and the graph (C21). Found: a test had
  written 2 nodes into the live graph. The test is fixed; deletion awaits ASK_ME A3.
  **Real runs are refused until then.**
- 1h: whole-trial NVML energy per trial (C20).
- Measured: retrieval energy per component (B 0.27 J, C 3.07 J, E rung 3 18.87 J net GPU per query;
  cross-encoder 8.72 J).
- `docs/RQ_READINESS.md` written.

**Blocked on Avaneesh:** `ASK_ME.md` (A1, A2, A3, G1, R1–R5, L1, L3, D4, D6, F1, S1, citations).

**Next** — Step 2 (confounds, dev/val only, freeze 9 Oct) after "go".

## 2026-10-05 (night) — Step 3: benchmark corrections (v1.1) and label review sheet

Branch `fix/benchmark-task-corrections` (WORK_PLAN step 6). PR #16 merged before.

**Done** (every change approved by Avaneesh, recorded per task: `human_approved_by`, date, reason)
- 4 tasks corrected against the pinned source: ops-053 (removal was Flask 2.3.0, not 3.0), ops-052
  (replaced a non-existent FastAPI error with the real `Cannot specify Depends in Annotated and default
  value together`, utils.py L368–371), code-014 (`dependency_cache`, not `values`), rev-045 (415/400/500,
  verified by executing Flask 3.0.3 + Werkzeug 3.1.9).
- 12 tasks: cited evidence moved to the verified locations (answers unchanged).
- Benchmark v1.0 → **v1.1** (split assignment unchanged); manifest hash → `149fa6bf2168fd14`.
- Labels rebuilt: 36 labels / 78 evidence spans / 0 open ground-truth issues / 0 spans without a chunk;
  ops-052 no longer flagged. `VERIFIED` record added (only Avaneesh's approvals mark a label verified).
- `docs/RETRIEVAL_LABELS_REVIEW.md`: question, answer and the real text of every labelled span.

**Next** — Avaneesh reviews the 36 labels; step 4: Mode R metrics.

---

## 2026-10-05 (night) — Step 2: own knowledge-graph builder; System D gets graph context

Branch `feat/knowledge-graph-wave1` (WORK_PLAN step 5). PR #15 merged before.

**Found in the existing graph code (master)** — all fixed: file ids embedded the commit so the
retriever never found a seed (0 graph chunks ever); module names via `rstrip(".py")` and `src/` kept,
relative imports ignored (imports never resolved); call targets in another id format, same file only;
"test" substring made all of `src/_pytest/` tests; Neo4j store read only OS env (not `.env`); the
in-memory store invented "Unknown" nodes for dangling edges; expansion walked through the Repository
hub, unordered, and injected chunks did not state the relation; no Git-history layer (plan §6.2).

**Done**
- `knowledge/graph/extractor.py` (repository-level: module map, src layout, relative imports, calls
  incl. methods/self/aliases, TESTS by naming convention, Git history with bulk-commit skip),
  `builder.py` (batched writes, read-back counts, history artifacts — commits/PRs/issues/ADRs/incidents
  ported with the new ids), Neo4j/in-memory `expand` (no hub crossing, all shortest connections) and
  `co_changed` (cosine of shared commits, ≥ 2), retriever ranking (other files first, nearest, then
  TESTS > IMPORTS > CALLS > CONTAINS) with relation-stating chunks, `scripts/build_graph.py`.
- `.corpus_cache` clones were shallow (1 commit each): deepened by 600 commits; HEAD and all files
  unchanged (verified per repo).

**Measured** (`experiments/results/graph_build/machine_A/graph_build_wave1.json`)
- 37,066 nodes (Repository 6, File 7,109, Class 4,071, Function 5,930, Method 9,187, Test 8,193,
  Commit 2,570) / 58,982 edges (CONTAINS 34,490, IMPORTS 5,414, CALLS 11,012, TESTS 1,952, MODIFIES
  6,114), read back from Neo4j = written; 0 dropped edges; 6,919 / 6,919 indexed files have a node;
  24 bulk commits skipped; 19 pylint files unparsable (intentional bad-syntax test data, py3.12 syntax).
- Graph preflight passes. Real query (Flask app context): 4 graph chunks (app.py imports, cli.py,
  app.py↔helpers.py co-changed in 20 commits, reqcontext.rst↔appcontext.rst) in ~277 ms retrieval.
- **Found for calibration (D17):** fused hybrid scores of the 36 dev+val questions are 0.58–0.96;
  with the fixed strategy thresholds 2–5 of 36 get zero evidence (e.g. a FastAPI question: all
  scores ≈ 0.57 < 0.60) — C/D would answer without evidence while B (no threshold) would not.
- Tests: **349 passed**.

**Next** — step 3 (benchmark fixes approved by Avaneesh + labels), then Mode R metrics.

---

## 2026-10-05 (night) — Step 1: chunk fix, re-ingest, Qdrant 1.15.1, line ranges in prompts

Branch `fix/ingestion-chunk-size` (WORK_PLAN step 4). PR #14 (audit) merged before.

**Done**
- Qdrant upgraded 1.13.2 → 1.14.1 → 1.15.1 on the same volume (48,046 points verified each hop;
  now from `docker-compose.yml`, healthy). Backup `C:\EIH_share\eih_knowledge_2026-10-05_qdrant-v1.13.2.snapshot`
  (sha256 `16d6dc42…258e38`, matches the server checksum).
- Chunker rewritten (plan §6.2 structure kept): BGE's own tokenizer, split oversized
  functions/methods/paragraphs/lines, nothing dropped, exact line ranges.
- Re-ingested into `eih_knowledge_v2`; collection name now only from `.env` (was hard-coded in 6 places).
- Retrieved chunks now carry start/end lines: before, the prompt showed no line ranges (no
  `[file:Lx-Ly]` citations possible) and the citation check accepted any cited line.
- Retrieval labels rebuilt against v2.

**Measured**
- Before: 3,485 of 48,046 chunks (7.3%) over BGE's 512 tokens (109 over 2,048).
- After: 53,905 chunks; 0 over 512 (max 512, p50 105, p95 502); 0 files with an uncovered
  non-blank line. Per repo: flask 1,615 · fastapi 20,353 · requests 1,036 · pytest 7,731 ·
  sphinx 10,701 · pylint 12,469 (ingest 311 s total).
- Retrieval check (report §10.3 query): same top-3 files (`docs/reqcontext.rst` L16–29,
  `tests/test_appctx.py` L32–35, `src/flask/ctx.py` L287–307).
- Labels: 36 labels / 76 evidence spans identical; every span still maps to ≥ 1 chunk
  (mean 1.92 → 2.14 chunks per span).
- Tests: **333 passed**.

**Benchmark** — 4 task corrections (ops-052, ops-053, code-014, rev-045) drafted with evidence and
**approved by Avaneesh**; applied in step 3 (`docs/BENCHMARK_FIXES_PROPOSED.md`).

**Next** — step 2: own knowledge-graph builder.

---

## 2026-10-05 (night, final) — restore-original-plan audit (one laptop from now on)

Branch `restore-original-plan` (from `feat/m5-live-calibration`; tag `pre-audit` = state
before). Avaneesh's decision: the whole project on this laptop only (WORK_PLAN C11).

**Done**
- Original plan frozen: `docs/original_plan.md` = the report's Markdown source as first
  committed (b249b2d), checked against the 25/26 Aug PDF text.
- Single config `configs/inference.yaml` for A–E + routing tiers; dead `configs/default.yaml`
  and paid-API models removed.
- Systems C–E now run the real task classifier (were given the answer key since 2026-08-20).
- Plan §9.1 tiers (CO₂e, cost ESTIMATED), CPU energy restored (ESTIMATED), §9.2 latency
  breakdown, truncation flag, untimed warm-up, RQ4 `system_e_routed`.
- Output limit back to the plan's 2,048; two-laptop tooling removed/archived; README title
  and RQ1–RQ8 restored; `docs/CITATION_AUDIT.md`.

**Measured** (laptop-a, dev split only, scratch output — smoke checks, not results)
- 12 units A/B/C × 4 tasks, max_output 1,024: 1 answer truncated at exactly 1,024 (A, task
  010), max prompt 2,002 tokens, no refusals; first retrieval 16–18 s (cold load).
- Same 12 units after the fixes, max_output 2,048: 0 truncated (task 010 completed at 1,134),
  retrieval 31–654 ms, warm-up 46.9 s recorded separately; manifest `42791f0b4216e66f`.
- Classifier vs benchmark labels on the 4 C trials: all 4 fields right on 1 task, 2 of 4 on
  two, 0 of 4 on one.
- Tests: full suite **323 passed**.

**Next** — step 4 (chunk fix + re-ingest), step 5 (own graph builder); decisions D3, D9,
D13–D16 in WORK_PLAN §4.

---

## 2026-10-05 (late night) — Full audit against the original plan + A3 integrity fixes

Branch `feat/m5-live-calibration` (task A3). Requested by Avaneesh: check everything
against the original plan, fix what can be fixed, one plan for both laptops.

**Audit findings**
- Two plans existed: `docs/WORK_PLAN.md` (A) and `docs/PROJECT_PLAN.md` on laptop-b's
  unmerged branch `docs/project-plan` (written in parallel, 01:36). That is the branch
  laptop-b could not merge (conflicts in CLAUDE.md/README). WORK_PLAN had also lost
  original-plan items (400–500 EIH-SWE tasks, licence audit, external Mode R/Q datasets,
  criticality slice, EIH-Fresh, systems studies). **WORK_PLAN rewritten as the single
  plan**: every original-plan and PROJECT_PLAN item kept (A7–A13, B7–B15), change
  register §7 (C1–C10), open decisions §6, ID mapping §8, two-laptop routine §9.
- My own fix `chore/git-sync-guard` c49800e (guard skips when the script is absent) was
  never merged → cherry-picked here `[must-pull]`.
- Laptop-b's F2/F3/F5 (energy labels) were still open; F4 was already resolved by Phase 1b.
- New silent defects in the M5 runner (all fixed, see Done).

**Done** (all verified by a real 4-unit job-queue smoke run on Ollama, dev split, scratch)
- Runner no longer invents numbers: local cost 0.0 had been replaced by gpt-4o-mini
  prices, missing energy/CO₂e by 45 W + 60 W × latency at the UK grid. Missing values now
  fail the trial (recorded as an error by the queue).
- Measured NVML energy, energy tier and max GPU temperature now reach `TrialResult`
  (smoke: 338–2,523 J measured per trial; an escalated System E trial with reranking
  correctly ESTIMATED); `cpu_energy_joules` None instead of TDP × latency.
- System A: no-retrieval prompt (smoke: answered with 482 / 166 tokens instead of
  refusing in ~1.5 s).
- Manifest built from runtime settings: hash `aa733133d041f11c` → **`bc6c83d062f075d9`**
  (7B, temp 0, num_ctx 12,288, 1,024 tokens, 713 g/kWh, 6 pinned repos, $0); job queue
  refuses a manifest/runtime mismatch.
- Systems D/E now get the Neo4j graph store (laptop-b's B3 finding: D equalled C); job
  queue graph preflight refuses D/E until the graph has all 6 repos — on this laptop it
  correctly refuses (0 Repository / 1 File node).
- EnergyEstimator F2/F3/F5 labels fixed. CLAUDE.md current state updated.
- Tests: 14 new; full suite **318 passed**.

**Must pull (Laptop B)** — `.claude/settings.json` (guard fix), `CLAUDE.md`,
`docs/WORK_PLAN.md` (single plan; replaces `docs/PROJECT_PLAN.md`).

**Blocked / for Laptop B** — B7 chunk fix and B1 ops-052/053 before A3's calibration run;
B3 F6 (Repository hub in graph expansion) before merge; B10 API graph store.

**Next**
- [ ] Restore `neo4j.dump` from laptop-b (copy to `C:\EIH_share\`), run graph preflight
- [ ] A3 calibration run on the 12 val tasks once B7 + ops-052/053 land
- [ ] Decisions D1, D3, D4, D9, D10 (WORK_PLAN §6) with Avaneesh

---

## 2026-10-05 (night) — Phase 1b step 7: GPU job queue

Branch `feat/gpu-job-queue` (off `feat/local-inference-routing`; task A2 step 7).

**Done**
- `scripts/job_queue.py`: one unit = (system, task, trial). Exactly-once ledger
  (`results.jsonl`, fsynced; re-running the same `--run-id` resumes, a half-written line
  from a crash re-runs), errors recorded with the exception (never dropped;
  `--retry-errors`), units interleaved and shuffled per trial round (seed 42) so no
  system always runs first/last, the 90 °C discard-cool-repeat rule (temperature read
  between units only), a GPU lock file, and the held-out test split only with
  `--final-test`, once. Writes `run.json` (provenance), `plan.jsonl`, `discarded.jsonl`,
  `summary.json` under `experiments/results/queue/<machine>/<run-id>/`.
- Tests: 11 new; full suite **267 passed**.
- Smoke run (2 dev tasks × baseline_a + system_e × 1 trial, real Ollama/Qdrant, written
  to scratch — not a result): 4/4 ok, resume re-ran 0 units.

**Found (for A3 — runner defects, not queue defects)**
- **System A refuses everything:** `BaselineRAGPipeline` with `skip_retrieval=True` still
  uses the evidence-only SYSTEM_PROMPT, so the 7B answers "INSUFFICIENT EVIDENCE" (~1.5 s,
  47–59 tokens) → A→B would measure a strawman. A needs its own no-evidence prompt.
- **Measured energy never reaches the trial record:** `M5BenchmarkRunner._evaluate_trial`
  sets `gpu_energy_measured_joules=None` and computes `cpu/gpu_energy_joules` as
  45 W / 60 W × latency; the NVML energy from `OllamaProvider` (and its per-call max
  temperature) is dropped. Must be wired before any A–E number counts.

**Next**
- [ ] Step 8: PRs (`feat/local-inference-routing` = step 6, then this branch)
- [ ] A3: fix the two runner defects above, manifest re-freeze, live calibration

---

## 2026-10-05 (evening) — Phase 1b step 6: long-context probe → context budget

Branch `feat/local-inference-routing` (task A2). Script `scripts/phase1_long_context_probe.py`.

**Decision (owner, 2026-10-05):** every model and system runs at **num_ctx 12,288, all
layers on the GPU (`num_gpu 999`), output limit 1,024 tokens** (was 4,096 / 2,048).
Thermal rule for long runs: work up to 90 °C; a condition with a call above 90 °C is
discarded and repeated after cooling to 65 °C.

**Measured** (laptop-a, encoders resident, real-corpus prompts, 1 cold + 2 warm per point)
- Prompt sizes (`long_context_sizes.md`): overhead 236 tokens; formatted chunk p50 117,
  p95 515, p99 903. DERIVED prompt for the widest rung (20–24 chunks): p95 5.5–6.4K,
  p99 7.5–9.0K tokens → fits 12,288 − 1,024.
- 7B all-on-GPU (`long_context_probe.md`): 4K 37.0 tok/s · 8K 35.4 · **12K 34.6 tok/s,
  peak 5,906 / 6,141 MiB, ~763 J/call** · 16K 33.1, VRAM full (6,088) · 20K prefill
  collapses 1,400 → 237 tok/s, 90 s, 3.2 kJ/call · 24K 170 s, 5.4 kJ/call. Ollama still
  reports 100% on GPU at 20K+: the WDDM driver pages to system RAM.
- 7B Ollama default placement: 82% → 64% on GPU as context grows; decode 20.1 → 3.3 tok/s.
- At 12K (`ctx12k_small_models/`): 1.5B 111 tok/s, peak 2,338 MiB; 3B 68.5 tok/s, peak
  3,368 MiB; both 100% on GPU.
- Routing switch 7B → 3B → 1.5B → 7B via the real provider at 12K with ~8.9K-token
  prompts: Ollama evicts the 7B for the smaller models and vice versa; every call 100% on
  GPU, context check headroom ~3,150 tokens.
- Tests: 256 passed (one test updated: all tiers now get `num_gpu 999`).

**Found**
- **81 corpus chunks are > 2,048 tokens, 9 are > 8,192, the largest 67,021** (lockfiles,
  contributor/sponsor lists, `plugin_list.rst`, a 39K-token test file). The prompt guard
  refuses such prompts (no silent truncation), but they must be fixed at ingestion — asked
  Laptop B (see Must pull / Blocked).
- At 24K the Qwen tokenizer counted 23 tokens more than Ollama (exact match up to 20K);
  over-counting is the safe direction for the truncation guard.

**Must pull (Laptop B)** — `core/config.py` max_tokens 2048 → 1024; `configs/models.yaml`
`num_gpu 999` for all three models; `OllamaProvider.DEFAULT_NUM_CTX` 4096 → 12288.

**Blocked / for Laptop B (before A3, ~14 Oct)**
- Re-chunk: cap chunks at ~512 tokens (BGE-small embeds only the first 512) and skip
  lockfiles / generated data; re-ingest, new snapshot in `C:\EIH_share\`, re-check labels.

**Next**
- [ ] Step 7: `scripts/job_queue.py`; Step 8: PR
- [ ] A3: correct and re-freeze the manifest (also stale: `model_max_tokens` 2048)

---

## 2026-10-05 — Phase 1b (steps 1–5 of 8): OllamaProvider, routing, escalation

Branch `feat/local-inference-routing` (task A2 in `docs/WORK_PLAN.md`).

**Done**
- **Decision:** Systems A–E use a fixed `qwen2.5-coder:7b`, all layers on the GPU;
  routing (1.5B→3B→7B) is an added system compared against it (RQ4).
- 7B option A measured (`vram_study_7b_forced_gpu.json`): forcing all layers onto
  the GPU fits and is faster and cheaper (numbers below).
- `OllamaProvider`: temperature 0 + seed 42, exact tokens, cold start measured
  separately, NVML energy per call (MEASURED), cost 0 (DERIVED), model digest,
  and it **refuses prompts that would be silently truncated** (exact Qwen
  tokenizer count matched Ollama 702 = 702).
- **Silent defects fixed:** pipelines and M5 runners fell back to `MockLLMProvider`
  when no OpenAI key was set (the final-test CLI would have run on the mock); the
  manifest's escalation limit never reached the pipeline; the `.env` escalation
  value was never read; `configs/default.yaml` is not loaded at runtime (labelled).
- `TierRouter` wired into `QualityAwareRAGPipeline`; tests assert the `model`
  field of every HTTP request actually sent. Escalation limit 2 → 3 (manifest hash
  `fcdbfa1b825d11e4` → `aa733133d041f11c`).
- Tests: **229 passed** (incl. live Ollama tests on this laptop).

**Measured** (Laptop A, warm n=5, ~1,338 prompt + 128 output tokens, num_ctx 4096)
- 7B default placement (82% on GPU): 22.1 tok/s, 390.1 ± 8.9 J per call
- 7B `num_gpu=999` (100% on GPU): **38.1 tok/s, 306.8 ± 11.8 J per call**, device
  peak 5,342 MiB of 6,141 with the encoders resident; reached 89 °C with hw thermal slowdown

**Must pull (Laptop B)**
- Defaults changed: provider `ollama`, model `qwen2.5-coder:7b`, temperature 0.
- **Edit your `.env`: `EIH_QUALITY_MAX_ESCALATION_ATTEMPTS=3`** (yours says 2, and
  `.env` values are now actually applied).
- Runs without an explicit provider now use the real Ollama; `--provider mock` only for tests.

**Next**
- [ ] Step 6: 20K-token long-context probe → set the context budget (needed before
      any real run: the final escalation rung can exceed num_ctx 4096) — STOP point
- [ ] Step 7: `scripts/job_queue.py`; Step 8: PR
- [ ] A3: correct and re-freeze the manifest (stale: gpt-4o-mini, temp 0.1, UK carbon,
      60 W, OpenAI prices, 2 repos)

---

## 2026-10-05 (later) — Two-laptop git sync guard

Branch `chore/git-sync-guard`.

**Done**
- PR #4 (Phase 1a) merged to `master` (`a29ccfa`).
- `scripts/git_sync_guard.py` + hooks in `.claude/settings.json`: at session start Claude fetches
  and reports what the other laptop merged; code edits are blocked while a must-pull change
  (`[must-pull]` tag or any shared-file change) is missing. 6 end-to-end tests on throwaway repos.
- CLAUDE.md session routine rewritten around the guard; WORK_PLAN §6 updated.

**Must pull** — this change itself is `[must-pull]`: Laptop B must `git pull` on master, then
restart Claude Code (or open `/hooks`) and approve the project hooks when asked.

**Next** — Phase 1b on `feat/local-inference-routing` once the 7B decision is made.

---

## 2026-10-05 — Phase 1a: local inference audit, energy meter, VRAM study

Branch `feat/local-inference` (task A1 in `docs/WORK_PLAN.md`).

**Done**
- Environment audit: RTX 4050 Laptop 6141 MiB, driver 617.14, NVML default power limit
  80 W (max 140 W); torch 2.6.0+cu124; Ollama 0.35.1; qwen2.5-coder 1.5b/3b/7b (all
  Q4_K_M) pinned by digest in `CLAUDE.md`. `.env`: `laptop-a`, CPU 45 W, GPU 60 → 80 W.
- **Bug fixed:** 8 settings groups never read `.env` (only OS env vars) on either laptop —
  TDP, carbon, quality, reranking and graph settings in `.env` were ignored. Now fixed,
  12 regression tests.
- New `NvmlEnergyMeter` (energy counter at start/end only), `experiments/provenance.py`
  (machine_id, GPU, torch/CUDA, Ollama digests, git SHA in every result), `Settings.machine_id`.
- **Measurement finding:** querying the GPU during a measurement perturbs the energy
  counter on this driver (power polling +9–12 W, counter polling +100 W; evidence in
  `experiments/results/phase1/machine_A/nvml_observer_probe.json`). First VRAM-study run
  discarded and re-run with the fixed meter.
- `docs/WORK_PLAN.md` created; README, ROADMAP, CHANGELOG, CLAUDE.md, report updated.

**Measured** (Laptop A, git `215a482`, `experiments/results/phase1/machine_A/vram_study.{json,md}`;
~1,338 prompt + 128 output tokens, num_ctx 4096, temp 0, seed 42; warm n=5, co-resident with encoders)
- 1.5B: 100% on GPU, device peak 1920 MiB, 131 tok/s, **105.7 ± 10.3 J** per call
- 3B: 100% on GPU, device peak 2870 MiB, 76 tok/s, **174.2 ± 10.7 J** per call
- 7B: **82% on GPU** (3992 of 4886 MiB), device peak 4806 MiB, 22 tok/s, **390.1 ± 8.9 J** per call
- Encoders (BGE-small + cross-encoder): +490 MiB device VRAM
- Test suite: 200 passed (Qdrant up) at `8378760`

**Next** (Phase 1b, branch `feat/local-inference-routing`)
- [ ] Decide 7B handling: A) force all layers on GPU (`num_gpu`) and measure, B) A + flash attention, C) accept 82%
- [ ] `OllamaProvider`; routing wired with per-call model-id logging and tests
- [ ] `max_escalation_attempts` 2 → 3 — NB `.env.example` now pins it (show manifest-hash change first)
- [ ] 20K-token long-context probe for the 7B KV cache (large-LLM baseline options)
- [ ] `scripts/job_queue.py`
- [ ] Re-measure reranker energy in batches (report §10.4 figures came from one power sample)

**Blocked / decisions needed**
- 7B handling (above). Large-LLM baseline strategy (dataset spec §7.3). Licence audit (§4.1).

---

## 2026-10-03 — Repository consolidated and shared

**Done**
- Committed ~70 files of uncommitted work from 26 Aug as 8 logical commits on
  `phase-2-intelligence`, to be shared with Laptop B via GitHub.
- Added `.gitattributes` (LF), hardened `.gitignore` (`.corpus_cache/`, snapshots,
  dumps, model weights).
- Test suite: **176 passed, 2 skipped** (the 2 need Docker Qdrant running).
- Added collaboration docs: `CLAUDE.md`, `SETUP_LAPTOP_B.md`, `docs/WORKFLOW.md`.
- Exported Qdrant `eih_knowledge` (48,046 points) to `C:\EIH_share\eih_knowledge.snapshot`
  (169 MB, SHA256 `a5b20b44…cbced7`); restore verified into a clean Qdrant v1.15.1.
  No Neo4j dump: the graph holds only a 2-node test fixture.

**State of the system**
- Implemented: ingestion, BGE embeddings (GPU), Qdrant, BM25 (corpus-backed),
  hybrid retrieval, cross-encoder reranker, knowledge graph, task classifier,
  adaptive retrieval, quality gate + escalation, NVML energy, region-aware CO₂e
  (India, 713 gCO₂e/kWh), M5 evaluation framework.
- Audit fixes: P0-1 (correctness in composite quality) and P0-2 (refusal credit
  capped, UNFOUNDED vs VALID refusal) applied with tests.
- Corpus wave 1 ingested: flask, fastapi, requests, pytest, sphinx, pylint —
  48,046 chunks.

**Not done / next** (superseded by the 2026-10-05 entry above)
- [x] Install Ollama + Qwen2.5-Coder 1.5B / 3B / 7B-Q4 (done 2026-10-04).
- [ ] Wire `routing/` into the pipeline (RQ4).
- [ ] P0-3: re-run validation calibration with a live local LLM; re-freeze manifest.
- [ ] Decide `max_escalation_attempts` 2 → 3 (reranking rung unreachable at 2).
- [x] Record `machine_id` automatically (`experiments/provenance.py`, 2026-10-05).
- [ ] Laptop A's existing `eih-qdrant` container (and its volume data) is still
      Qdrant **v1.13.2**, while `docker-compose.yml` pins v1.15.1. Do NOT run
      `docker compose up` on it blindly (that jumps two minor versions on the stored
      data); use `docker start eih-qdrant` for now, then either upgrade via 1.14.x
      or recreate the volume from `C:\EIH_share\eih_knowledge.snapshot`.
- [ ] First real Mode R / Mode Q run of Systems A–E (dev split only).

**Blocked / decisions needed**
- Large-LLM baseline strategy (dataset spec §7.3).
- Licence audit for external datasets (dataset spec §4.1).
