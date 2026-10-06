# ASK_ME: open decisions for Avaneesh

Each item gives the exact question and a recommended default. Work continues on other steps
until you answer. To answer, reply with the item ID and your choice. Answered items move to
"Decided" with the date.

## Capacity (from `docs/SCHEDULE.md`)

- [x] **G1: GPU shortfall. Closed by C31 (no deadlines):** every run keeps its full trials and runs
  until done (`docs/SCHEDULE.md` §3 gives the expected GPU hours).
- [ ] **G2: Skip Mode Q on the ~234 newly approved dev/val tasks (35 GPU-h)?** No claim uses
  dev results; calibration uses val. **Recommended: skip; run only if the GPU is idle.**
- [ ] **R1: Review pace (updated after C31: no deadlines).** Queue today: 160 items (10 calibration,
  36 labels, 20 audit fixes, 24 test tasks needing 2 reviews each, 70 drafts), plus 40 blind ratings
  × 2. At 4 reviewers × ~25 reviews/day, reaching ~450 tasks takes about 10 working days of review.
  There is no date to hit, but final runs on a set cannot start until its review is finished.
  **Recommended:** review in queue order (ratings and test-task pass first), and add reviewer hours
  if you want the final runs sooner. Claude drafts ~80–90 tasks/day so drafting never limits.
- [ ] **R3: Reviewer full names.** These are recorded in `human_approved_by` and in the paper.
  `benchmark/data/review/reviewers.yaml` has "Sanvi", "Aayan", "Radhesh". Please give full names.
- [ ] **R5: Who is "lead_researcher"?** 44 pilot tasks carry `human_approved_by:
  "lead_researcher"`. If that is Avaneesh, he cannot decide on the calibration batch (drafted by
  "lead_researcher"), and those tasks have no independent approval.
  **Recommended: say who it was.** If it was Avaneesh, the 10 calibration tasks are reviewed by
  the other three, and kappa is computed over three raters.

## Benchmark and labels

- [ ] **L2: Approval of drafted tasks.** Every LLM-drafted task stays "drafted" until a human
  approves it in the review queue (`docs/REVIEW_GUIDE.md`). Confirm the four checks and the
  approve/fix/reject outcomes as written. **Recommended: confirm.**
## Plan decisions still open (WORK_PLAN §4)

- [x] **D3: Closed by C31** (no deadlines).
- [ ] **F2: EIH-Fresh back to ~150 tasks?** C27 cut it to 50 only because review hours to 12 Oct
  did not fit 150. With no deadline that reason is gone. 150 tasks need ~300 reviews (2 each).
  **Recommended: yes, ~150**, as the dataset spec says; more tasks give RQ7 real power.
- [ ] **P2: Mode P scope.** D6 chose "Defects4J subset first, rest after" because of 20 Oct. Without
  a deadline: run all eight Mode P sets in the planned order? They are a guessed ~1,300 GPU-h
  (weeks of GPU time). **Recommended: Defects4J in full first, measure the real time per attempt,
  then decide on the rest.**
- [ ] **D10: Delete old merged branches.** Needs your OK.
- [ ] **D13: Count mismatches in the original documents** (300–450 vs 400–500 tasks; 28 vs 26
  repos; 21 vs 22 task types). **Recommended:** the spec's locked 400–500 is binding; correct the
  two counts in the paper.

## Citations

- [ ] **C-9, C-10: References [9] and [10]** could not be found (`docs/CITATION_AUDIT.md`).
  Please supply the exact title, authors, venue and DOI, or tell me to remove them. No
  replacement will be invented.
## For information (no answer needed)

- No hash lock (C30). **Test-task corrections from the two-reviewer pass must still be applied before
  the test split's final run**, which happens exactly once.

- Output limit: the master prompt lists 1,024 tokens as provisional. The logs show that 1,024
  cut off a real answer (System A, task req-010: stopped at exactly 1,024; it completed at 1,134).
  So it was raised to the plan's 2,048 for all systems (WORK_PLAN C17, `configs/inference.yaml`).
  Its smoke run was rerun.
- Run-to-run variation at temperature 0 / seed 42 also appears in the 5 Oct smoke runs. B on
  req-010 gave 981 vs 853 output tokens; A on req-008 gave 482 vs 347. Step 2c measures it.
- Step 1c installs `statsmodels` (mixed-effects models for RQ5) and adds it to the requirements.

## Decided

- 2026-10-06 (Step 3 "go"):
  - **M1** approved with guardrails: candidate correctness measures are compared against 30–50 blind
    human ratings; the measure is chosen by agreement with humans BEFORE any system-level comparison;
    raters never see the system; the threshold is set on dev/val from the human ratings; token F1 is
    reported alongside.
  - **T1**: keep 2,048; the routing-tier loops are reported as a measured failure.
  - **V1**: keep 3 trials and report the variance.
  - **Audit fixes**: all go into the review queue; nothing is applied before a human verifies them
    against the pinned code; test-task fixes need two reviewers.
  - **Decision table**: L1 (via the queue), L3 (after review), D4 (7B at full context + published
    figures labelled "not measured here", never compared as if run locally), D6, D14 ("completeness
    (proxy)"), F1 (EIH-Fresh 50, change C27), S1, R2, R4, RQ6 = google/gson + expressjs/express,
    citation [2] = arXiv 2601.02522 (venue only once confirmed).
  - **Freeze**: one change set (M1 + verified audit fixes + verified label changes), then one dev/val
    rerun and a re-freeze.
  - **Classifier**: no further tuning.
- D9 (Qdrant 1.15.1) was done before Step 1; the client warns 1.19 vs server 1.15.1, which works.

- 2026-10-06 **A3**: backup exported (`C:/EIH_backups/neo4j_graph_pre_A3_2026-10-06.jsonl.gz`), then
  `test:node:a`, `test:node:b` and their edge deleted. The graph now equals its build record
  (37,066 / 58,982, labels and edge types identical). The log is
  `experiments/results/graph_build/machine_A/graph_maintenance_2026-10-06_A3.json`. The full test
  suite leaves the live graph unchanged.
- 2026-10-06 **A1**: System D adds graph context on every task (WORK_PLAN C23).
- 2026-10-06 **A2**: success = correct AND cites labelled evidence lines.
- 2026-10-06 **D12**: two independent reviewers (from Avaneesh, Sanvi, Aayan, Radhesh) check the
  test tasks' correctness before any tuning sees the test split.

- 2026-10-05: four benchmark fixes (ops-052, ops-053, code-014, rev-045) and 12 evidence fixes,
  approved by Avaneesh (`docs/BENCHMARK_FIXES_2026-10-05.md`, PR #17).
- 2026-10-05: provisional settings num_ctx 12,288, all layers on the GPU (C4).
