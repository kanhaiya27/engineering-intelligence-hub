# ASK_ME: open decisions for Avaneesh

Each item gives the exact question and a recommended default. Work continues on other steps
until you answer. To answer, reply with the item ID and your choice. Answered items move to
"Decided" with the date.

## Capacity (from `docs/SCHEDULE.md`)

- [ ] **G1: GPU shortfall.** The full Mode R/Q scope needs ≈ 550 GPU-hours. About 300 are available
  to 20 Oct, and Mode P needs ~1,300 more (unmeasured guess). Which fix?
  (a) External Mode Q sets (CodeRepoQA, StackRepoQA, Big-Vul/PrimeVul) at **1 trial** instead of 3.
      Run-to-run variance is measured on EIH-SWE, which keeps 3 dev/val trials and N = 5 on test.
      This saves ≈ 265 h and makes R/Q fit with almost no slack.
  (b) Add a second GPU machine for external runs only, with the same config and manifest hash.
  (c) Keep full trials and let the external runs finish after 20 Oct, inside the 21–25 Oct buffer and then November.
  **Recommended: (a) + (c) for whatever is left.** Mode P: see D6.
- [ ] **G2: Skip Mode Q on the ~234 newly approved dev/val tasks (35 GPU-h)?** No claim uses
  dev results; calibration uses val. **Recommended: skip; run only if the GPU is idle.**
- [ ] **R1: Review shortfall.** ~1,000 reviews ≈ 135 h are needed. 4 × 3 h × 7 days = 84 h.
  Which fix?
  (a) Avaneesh adds ~6 h/day as the fourth reviewer.
  (b) Reviewing continues to 14 Oct and the lock moves to 14 Oct.
  (c) A lower EIH-SWE target. Not recommended; that would be a scope change.
  **Recommended: (a).** Re-check after day one with the measured minutes per review.
- [ ] **R2: Who requests drafted batches?** The no-self-approval rule also excludes the person
  who *requested* a draft. If Avaneesh requests every LLM draft, he can never review new tasks.
  **Recommended: the requester rotates per batch** (that person chooses the repository and stage
  for the batch, and the other three review it).
- [ ] **R3: Reviewer full names.** These are recorded in `human_approved_by` and in the paper.
  `benchmark/data/review/reviewers.yaml` has "Sanvi", "Aayan", "Radhesh". Please give full names.
- [ ] **R4: How reviewers reach the queue.** (a) On this laptop in turns. (b) Each reviewer on
  their own clone, committing only `benchmark/data/review/decisions/<name>.jsonl`; files never
  conflict, and Avaneesh merges. **Recommended: (b)** for Sanvi/Aayan/Radhesh. This is review data
  only: no code or results come in from other laptops.
- [ ] **R5: Who is "lead_researcher"?** 44 pilot tasks carry `human_approved_by:
  "lead_researcher"`. If that is Avaneesh, he cannot decide on the calibration batch (drafted by
  "lead_researcher"), and those tasks have no independent approval.
  **Recommended: say who it was.** If it was Avaneesh, the 10 calibration tasks are reviewed by
  the other three, and kappa is computed over three raters.

## Benchmark and labels

- [ ] **L1: Retrieval labels (VERIFIED list).** Review `docs/RETRIEVAL_LABELS_REVIEW.md`
  (36 dev/val labels). Reply with the task numbers that are wrong. All others are recorded as
  verified by you. Mode R numbers stay "draft labels" until then.
- [ ] **L2: Approval of drafted tasks.** Every LLM-drafted task stays "drafted" until a human
  approves it in the review queue (`docs/REVIEW_GUIDE.md`). Confirm the four checks and the
  approve/fix/reject outcomes as written. **Recommended: confirm.**
- [ ] **L3: 9 dev/val tasks cite a doc file with no line numbers** (dev-021, dev-028, dev-030,
  ops-058, req-002, req-008, rev-046, test-034, test-038). This breaks Hard Rule 3. Their retrieval
  labels have line spans.
  **Recommended: take the lines from the label, check them in review, and write them into the
  task file after approval** (Step 2d). The same check runs on the test tasks in the 3b
  correctness pass.
- [ ] **F1: EIH-Fresh size.** The master prompt says 30–50 tasks; the dataset spec (Tier 3) says
  ~150. **Recommended: 50 by 12 Oct, recorded as change C19 in WORK_PLAN.** 150 needs ~200 more
  reviews and +25 GPU-h.
- [ ] **S1: Split rule for new EIH-SWE tasks.** **Recommended:** a deterministic stratified split
  (seed 42) per SDLC stage × repository, in the pilot's ratio 40% dev / 20% val / 40% test. It is
  assigned when a task is approved, so nobody chooses where a task lands.

## Design decisions found in Step 1

## Plan decisions still open (WORK_PLAN §4)

- [ ] **D4: Large-LLM baseline** (spec §7.3; a large model cannot run on 6 GB).
  (a) Cite published figures, marked as not measured.
  (b) A one-off paid API run. This breaks the local-only lock and its energy cannot be measured.
  (c) The 7B with full context as the "send everything" baseline.
  **Recommended: (c) + (a)**, as the spec recommends.
- [ ] **D6: Mode P owner and scope.** Defects4J needs a JDK, the Defects4J framework and a test
  harness. SWE-bench-family sets need per-repo Docker images: hundreds of GB, and ~1,300 GPU-h at
  a guessed rate.
  **Recommended:** Claude builds the harness, Avaneesh owns its decisions. Defects4J first on a
  stratified subset by 20 Oct; the rest continues in November. Per the plan, Mode P "cannot
  invalidate the primary results".
- [ ] **D14: Completeness metric** (plan §9.2). **Recommended:** report evidence coverage as
  "completeness (proxy)" and label it so; no new evaluator.
- [ ] **D3: What "experiments complete" means on 25 Oct** (supervisor). The schedule now targets
  20 Oct for everything; G1 and D6 decide what is realistic.
- [ ] **D9: Qdrant v1.13.2 → v1.15.1 upgrade.** It recreates the container (snapshot first).
- [ ] **D10: Delete old merged branches.** Needs your OK.
- [ ] **D13: Count mismatches in the original documents** (300–450 vs 400–500 tasks; 28 vs 26
  repos; 21 vs 22 task types). **Recommended:** the spec's locked 400–500 is binding; correct the
  two counts in the paper.

## Citations

- [ ] **C-9, C-10: References [9] and [10]** could not be found (`docs/CITATION_AUDIT.md`).
  Please supply the exact title, authors, venue and DOI, or tell me to remove them. No
  replacement will be invented.
- [ ] **C-2: Reference [2]'s DOI 10.1145/3786581.3786932** is unconfirmed, and the venue appears
  to be ICSE-SEIS, not the main track. **Recommended:** cite the arXiv ID 2601.02522 and state
  the venue only once it is confirmed.

## RQ6 repositories

- [ ] **L6: Non-Python repositories for RQ6.** `datasets/registry.yaml` (the plan's 4 waves)
  names Java (gson, commons-lang, jackson-databind, jsoup, mockito), JavaScript (express, axios),
  TypeScript, Go (gin, cobra), Rust (serde, clap), C++ (nlohmann/json) and C (zstd).
  **Recommended: google/gson (Java) and expressjs/express (JavaScript)**, both in the registry.
  Add more only if review hours allow.

## For information (no answer needed)

- Output limit: the master prompt lists 1,024 tokens as provisional. The logs show that 1,024
  cut off a real answer (System A, task req-010: stopped at exactly 1,024; it completed at 1,134).
  So it was raised to the plan's 2,048 for all systems (WORK_PLAN C17, `configs/inference.yaml`).
  Its smoke run was rerun.
- Run-to-run variation at temperature 0 / seed 42 also appears in the 5 Oct smoke runs. B on
  req-010 gave 981 vs 853 output tokens; A on req-008 gave 482 vs 347. Step 2c measures it.
- Step 1c installs `statsmodels` (mixed-effects models for RQ5) and adds it to the requirements.

## Decided

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
