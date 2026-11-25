# ASK_ME: open decisions for Avaneesh

Each item gives the exact question and a recommended default. Work continues on other steps
until you answer. To answer, reply with the item ID and your choice. Answered items move to
"Decided" with the date.

## Capacity (from `docs/SCHEDULE.md`)

- None open (G1, G2, R1, R3, R5 answered 2026-11-25; see Decided).

## Benchmark and labels

- None open (L2 answered 2026-11-25; see Decided).

## Plan decisions still open (WORK_PLAN §4)

- [x] **D3: Closed by C31** (no deadlines).

- [ ] **T16: Tree-sitter chunking (step 16) and the frozen wave-1 corpus.** Wave 1 already holds 1,869
  chunks of non-Python source code (JS, C, …, `ingestion_report.json` "doc:source_code"), cut by the
  generic splitter. Tree-sitter would chunk them differently, so applying it to wave 1 changes the corpus
  (53,905 points, bound in the manifest) and every dev/val result made on it. Options: (a) tree-sitter
  only for new waves 2–4 (wave 1 unchanged); (b) also re-chunk wave 1 into a new `eih_knowledge_v3`
  and re-run dev/val before any comparison. **Recommended: (a)** for the A–E comparison on wave 1, and
  report the chunker per wave; (b) only if you want one chunker everywhere (costs the dev/val reruns).

## Citations

- None open (C-9, C-10 answered 2026-11-25; see Decided). D15 stays open for citation [2]'s DOI.

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

- 2026-11-25 (team answers to all open items): decided by CODE RAD for the team, with Avaneesh.
  - [x] **G1**: closed by C31.
  - [x] **G2**: skip Mode Q on the ~234 newly approved dev/val tasks. Run them only if the GPU is
    otherwise idle. No claim may use them (WORK_PLAN C35).
  - [x] **R1**: review in queue order at the current pace: blind ratings and the test-task
    correctness pass first. No extra reviewer hours (C36). With 3 reviewers instead of 4 the review
    takes longer. At 3 × ~25 reviews/day (~75/day), R1's ~1,000 reviews take about 13–14 working
    days instead of ~10 (ESTIMATED). With R5 and F2 added (~1,250 reviews) it is about 17 working
    days (ESTIMATED; `docs/REVIEW_GUIDE.md`).
  - [x] **R3**: the reviewers are **Sanvi Bhardwaj, Aryan Gupta, Avaneesh Kumar Verma**. Aayan and
    Radhesh are removed (C36). **Disclosure for the paper:** one of the three benchmark reviewers,
    Aryan Gupta, is the project's supervisor (Mr. Aryan Gupta, UPES, the project guide), and Avaneesh
    Kumar Verma is the system's developer (`docs/PROJECT_REPORT.md` §12). Every queue and rating slot
    of Aayan or Radhesh was reassigned (seed 42, load-balanced). No decision or rating had been
    recorded by anyone, so none was superseded.
  - [x] **D12 note (2026-11-25)**: the 2026-10-06 D12 entry below is kept as it was. The reviewer
    pool for the test-task pass is now Sanvi Bhardwaj, Aryan Gupta and Avaneesh Kumar Verma.
  - [x] **R5**: "lead_researcher" was all three reviewers jointly (Sanvi Bhardwaj, Aryan Gupta,
    Avaneesh Kumar Verma). A joint approval is not an independent one, so each of the three
    re-reviews, blind and independently, the 44 pilot tasks with `human_approved_by:
    "lead_researcher"`, which include the 10 calibration tasks. Agreement on them is Fleiss' kappa
    over 3 raters. `human_approved_by` is updated only after the re-review (C37). Queue:
    `calibration-01` (10), `r5-independent-01` (10), `test-correctness-01..04` (24; see C37 for the
    third test-task review).
  - [x] **L2**: the drafted-task approval rules in `docs/REVIEW_GUIDE.md` (four checks;
    approve/fix/reject) are confirmed as written.
  - [x] **F2**: EIH-Fresh goes back to ~150 tasks (~300 reviews at 2 each). Reverses C27 (C38).
  - [x] **P2**: Mode P runs a seeded random sample of ~50 bugs per set, across all 8 Mode P sets and
    all systems (seed 42). Supersedes D6 / C28 "Defects4J first" (C39). The sampling plan is
    `docs/MODE_P_SAMPLE.md`, fixed before any run. GPU: rough estimate 200–300 GPU-h (ESTIMATED),
    to be re-measured on the first set.
  - [x] **D10**: delete merged branches only; keep every unmerged branch. The exact deletion list
    waits for explicit approval (PR description); nothing has been deleted.
  - [x] **D13**: the dataset spec is binding: EIH-SWE is 400–500 tasks. The paper text is corrected
    to the real data: 26 repositories in 8 languages (`datasets/registry.yaml`) and 22 task types plus
    `unknown` (`knowledge/schemas/tasks.py` `TaskType`, 23 values) (C40).
  - [x] **C-9, C-10**: references [9] and [10] are removed (C41, `docs/CITATION_AUDIT.md`). The frozen
    `docs/original_plan.md` still cites them.

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
