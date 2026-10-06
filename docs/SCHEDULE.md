# EIH work order and budgets

**No deadlines (C31, 2026-10-06).** Avaneesh removed every date from the plan (the 20 Oct target,
the 21-25 Oct buffer, the 25 Oct paper and 15 Nov project dates, the 9 Oct freeze and 12 Oct
reviewer dates). Work runs in the order below until it is done. Full scope stays (RQ1-RQ8,
Systems A-E + routing, Modes R/Q/P, large-LLM baseline, EIH-SWE ~450, RQ6, EIH-Fresh, external
datasets, paper, report). Nothing is cut to save time.

## 1. Order of work

Steps are done one at a time with a stop and a "go" after each (master prompt rule 8).

| Step | Work | Status |
|---|---|---|
| 0-1 | Schedule, review tool, measurement validity | Done |
| 2 | Design fixes and calibration on dev/val; config frozen (manifest `95e5a587c9d60e7a`) | Done |
| 3 | Benchmark: drafting tool, review queue, blind M1 ratings, power check | Tools done; review not started |
| - | M1 change set (new correctness measure + verified audit/label fixes), one dev/val rerun, re-freeze | Waits on ratings and reviews |
| 4 | RQ6: Java (gson) + JavaScript (express) ingestion, graph, ~60 reviewed tasks | Not started |
| 5 | EIH-Fresh collection and review | Not started |
| 6 | External datasets (licence audit, then Mode R/Q) and Mode P harness | Not started |
| 7 | Final runs on held-out sets, each exactly once, on the frozen config | Not started |
| 8 | Statistics, figures, paper, project report | Not started |

A held-out set (EIH-SWE test, RQ6, Fresh, external slices) is run once its review is finished
and the config is frozen; there is no lock date (C30).

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

**Duration, not a deadline:** the R/Q subtotal is ≈ 550 GPU-h at the 30 s planning rate. The
measured rate in Step 2c was 20.6 s per unit (648 units in 3.7 h of wall time), so it is likely
nearer 380 GPU-h, i.e. roughly two to three weeks of the GPU running around the clock with cooling. Mode P comes on top. Without a
deadline every run keeps its full trials.

## 4. Review budget and quotas

**Pace:** 4 reviewers × ~3 h a day, plus any extra hours the lead researcher gives.

**Needed (planning figure ~8 min per review; replaced by the day-one measured mean):**

| Work | Reviews |
|---|---|
| Day-one calibration (10 × 4) | 40 |
| Existing 24 test tasks, two reviewers each | 48 |
| New EIH-SWE tasks to reach ~450: ~390 approved; ~520 drafts at a 25% reject rate; 40% are test tasks needing two reviews | ~730 |
| RQ6 tasks (~60, 40% two reviews) | ~85 |
| EIH-Fresh (50, all held out, two reviews) | 100 (300 at ~150 tasks) |
| **Total** | **~1,000 reviews ≈ 135 h** |

At ~100 reviews a day this is about 10 working days of review (more if Fresh is ~150).

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
   (§3 shows the expected total).
5. Blockers: every open `- [ ]` item in `ASK_ME.md`.
