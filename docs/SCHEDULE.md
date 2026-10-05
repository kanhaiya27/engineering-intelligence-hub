# EIH schedule to 20 October 2026

Written 5 Oct 2026 (master prompt of 5 Oct). Target: everything done by **Tue 20 Oct**;
21–25 Oct is buffer only. Paper due Sun 25 Oct; whole project due 15 Nov. Full scope stays
(RQ1–RQ8, Systems A–E + routing, Modes R/Q/P, large-LLM baseline, EIH-SWE ~450, RQ6, EIH-Fresh,
external datasets, paper, report).

**Bottom line: the full scope does not fit by 20 Oct on one laptop GPU.** The shortfall is
in §3 (GPU) and §4 (review hours). The smallest honest fixes are decisions for Avaneesh, listed
in `ASK_ME.md`. Nothing is cut until he decides.

## 1. Fixed dates

| Date | Event |
|---|---|
| Mon 5 Oct | Steps 0–1 (schedule, review tool, measurement validity) |
| Tue 6 Oct | Day-one reviewer calibration (`calibration-01`, 10 tasks × 4 reviewers, Cohen's kappa) |
| Tue 6 – Wed 7 Oct | Correctness pass on the 24 existing test tasks (2 reviewers each), **before any tuning** (3b) |
| Fri 9 Oct | Config freeze: one config for A–E and every routing tier, hashes recorded (Step 2e) |
| Mon 12 Oct | Reviewers' last day; **all sets locked by hash** (EIH-SWE splits, EIH-Fresh, RQ6 tasks, external slices) |
| Mon 12 – Mon 19 Oct | Final runs, unattended 24 h/day with resume (job queue) |
| Tue 20 Oct | Final statistics, figures, paper + report drafts complete |
| 21–25 Oct | Buffer only |

## 2. Day by day (three tracks)

Track 1 = code and runs. Track 2 = data and review. Track 3 = writing. "GPU night" = the
job queue runs unattended overnight.

| Day | Track 1 (code/runs) | Track 2 (data/review) | Track 3 (writing) | GPU |
|---|---|---|---|---|
| Mon 5 | Step 0; Step 1 (metrics, stats, manifest, energy) | Review tool; calibration batch queued | — | Mode R dev/val; retrieval-energy batches |
| Tue 6 | Step 2a classifier accuracy; 2b threshold calibration on dev/val | **Calibration 10 tasks × 4**; kappa; test correctness pass starts (24 × 2) | — | Calibration candidates (val), 3 trials |
| Wed 7 | Step 2c variance (3+ trials); Step 3a drafting tool; Step 6 licence audit | Test pass done; first drafted batches (25 each) | — | Variance study; ingest RQ6 repos |
| Thu 8 | Step 2d dev/val audit (`BENCHMARK_AUDIT.md`); Step 4 tree-sitter (Java, JS) | Batches; reject-rate check | Method, benchmark, metrics | Mode Q dev/val (A–E + routing × 3) |
| Fri 9 | **Freeze config (2e)**; Step 4 graph build for RQ6 repos | Batches; RQ6 task drafts | Statistics, threats to validity | Ingest external corpora (passed licences) |
| Sat 10 | Step 5 EIH-Fresh collection (post-cutoff repos); Mode P harness (D6) | Batches; Fresh drafts (2 reviewers each) | Related work, citations [2]/[9]/[10] | External Mode R (RepoBench, CrossCodeEval) |
| Sun 11 | Large-LLM baseline setup (D4); power check (3d) | Batches; Fresh review | Limitations, non-claims | Big-Vul/PrimeVul slice (after freeze) |
| Mon 12 | **Lock all sets by hash (3e)**; start final test queue | Last review day; final counts | — | **EIH-SWE test, N = 5** |
| Tue 13 – Thu 15 | Monitor queue, thermal rule, resume | — | Results tables fill as runs finish | Test split → RQ6 → EIH-Fresh |
| Fri 16 – Mon 19 | External Mode Q, large-LLM baseline, Mode P | — | Results, discussion | CodeRepoQA, StackRepoQA, Mode P |
| Tue 20 | Step 7e: statistics, RQ5–7 analysis, figures | — | **Paper + report complete** | — |

Steps are still done one at a time with a stop and a "go" after each (master prompt rule 8). The
table shows when each must start for the date to hold.

## 3. GPU-hour budget

**Planning rate:** 30 s per Mode Q unit (one system × one task × one trial), i.e. 120 units per
GPU-hour. Source: the dev smoke runs of 5 Oct (`audit-check2`, `smoke2`; n = 16 units, current
config). Mean wall time per trial:
- A: 12.5 s
- B: 16.5 s
- C: 11.1 s
- E: 35.1 s, up to 62 s with 3 escalations

Overhead is added for cooling (90 °C rule), queue and warm-up. These are **planning figures from
smoke runs, not results**. They are replaced by the measured rate after the Mode Q dev/val run.
The dataset spec (§2) assumed 4 s per generation. The measured mean is about 5× that, which is
why its "6.5 GPU-days" estimate no longer holds.

Embedding (ingestion) measured at ~170 chunks/s: the 53,905 wave-1 chunks took 311 s
(`experiments/results/ingestion_report.json`).

Systems = 6 (A, B, C, D, E, E + routing). Trials as in the plan: 3 on dev/val, **N = 5 on the
final held-out test** (plan Phase 10).

| Run | Tasks | Systems | Trials | Units | GPU-h |
|---|---|---|---|---|---|
| Mode R dev/val (1a) + retrieval energy (1h) | 36 | B, C, D, E rungs | 1 / batches | — | ~1 |
| Calibration on val, ~3 candidate configs (2b, 2e) | 12 | 6 | 3 | 648 | 5.4 |
| Run-to-run variance (2c) | 24 | 6 | 3 | 432 | 3.6 |
| Mode Q dev/val, frozen config (7a) | 36 | 6 | 3 | 648 | 5.4 |
| Mode Q on newly approved dev/val tasks (not needed for any claim) | ~234 | 6 | 3 | 4,212 | 35 |
| **EIH-SWE test, final** (≈40% of ~450) | ~180 | 6 | 5 | 5,400 | 45 |
| Large-LLM baseline (D4; 7B at full context) | ~180 | 1 | 5 | 900 | 7.5 (×5 if a CPU-offloaded 14B) |
| RQ6 multi-language tasks (Step 4) | ~60 | 6 | 5 | 1,800 | 15 |
| EIH-Fresh (Step 5): 50 tasks / the spec's ~150 | 50 / 150 | 6 | 5 | 1,500 / 4,500 | 12.5 / 37.5 |
| CodeRepoQA, Mode Q (spec: 1,000 stratified) | 1,000 | 6 | 3 | 18,000 | 150 |
| StackRepoQA, Mode Q (spec: 1,318) | 1,318 | 6 | 3 | 23,724 | 198 |
| RepoBench + CrossCodeEval, Mode R | 2,000 | 4 retrieval configs | 1 | — | ~2 |
| Big-Vul + PrimeVul, criticality slice (RQ4) | 1,000 | E, E + routing | 3 | 6,000 | 50 |
| Ingestion: RQ6 repos + external corpora (incl. 134 StackRepoQA repos) | — | — | — | — | ~10–20 |
| **Subtotal (Mode R/Q, classification)** | | | | | **≈ 550** |
| Mode P: Defects4J 835, BugsInPy 493, CodeFlaws 500, SWE-bench Lite 300, Pro 731, SWE-rebench 500, Multi-SWE-bench flash 300, SWE-bench Multilingual 300 | 3,959 | ≥ 2 | 1 | ~7,900 | **unmeasured; ~1,300 at a guessed 10 min per attempt** |

**Available:** 6–20 Oct ≈ 14.5 days × 24 h × ~0.85 usable (cooling, restarts, ingestion
contention) ≈ **300 GPU-hours**.

Only runs on frozen, locked sets count as final. Those can start on 9 Oct (external sets,
after the freeze) or 12 Oct (EIH-SWE test, RQ6, Fresh, after the lock). That leaves ≈ 230 GPU-h
for them.

**Shortfall:** about 250 GPU-h for Modes R/Q and classification, plus all of Mode P. The options
are in `ASK_ME.md` (G1). The schedule will not quietly drop runs.

## 4. Review budget and quotas

**Available:**
- 4 reviewers × ~3 h × 7 days (6–12 Oct) = **84 h**
- plus whatever extra hours the lead researcher gives

**Needed (planning figure ~8 min per review; replaced by the day-one measured mean):**

| Work | Reviews |
|---|---|
| Day-one calibration (10 × 4) | 40 |
| Existing 24 test tasks, two reviewers each | 48 |
| New EIH-SWE tasks to reach ~450: ~390 approved; ~520 drafts at a 25% reject rate; 40% are test tasks needing two reviews | ~730 |
| RQ6 tasks (~60, 40% two reviews) | ~85 |
| EIH-Fresh (50, all held out, two reviews) | 100 (300 at ~150 tasks) |
| **Total** | **~1,000 reviews ≈ 135 h** |

**Shortfall:** about 50 h (more if Fresh is ~150). Options are in `ASK_ME.md` (R1).

**Daily quota per reviewer:** one batch of 25 (≈ 3 h at 7–8 min). With four reviewers that is
100 reviews a day. It is re-set after day one from the measured minutes per review
(`python scripts/review.py report`).

**Rotation:**
- Batches rotate so that no one decides on a batch they drafted or requested (the tool enforces this).
- Every held-out item gets two different reviewers.

## 5. Daily progress report (posted each evening)

Produced by `python scripts/review.py report --day YYYY-MM-DD` plus the job-queue ledgers:

1. Approved tasks: total, per SDLC stage, per repository, per reviewer.
2. Decisions per reviewer, minutes per reviewer, mean minutes per review.
3. Reject rate. **Alert above 30%**: fix the drafting prompt; never loosen approval.
4. GPU hours used that day (sum of trial wall times in `experiments/results/queue/*/*/results.jsonl`)
   against the §3 budget.
5. Blockers: every open `- [ ]` item in `ASK_ME.md`.
