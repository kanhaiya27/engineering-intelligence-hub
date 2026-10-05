# RQ readiness

Updated after Step 2 (6 Oct 2026, branch `master-fix`, frozen manifest `95e5a587c9d60e7a`). One entry per
research question (`docs/original_plan.md` §3). The original plan states no formal hypotheses beyond
RQ1–RQ8 and contributions C1–C4.

**Evidence so far, all dev/val only (no test task has been run or read):**

| Source | Location | Status |
|---|---|---|
| Mode R, after A1 and 2b | `experiments/results/mode_r/machine_A/mode-r-devval-2026-10-06-2b/` | **PROVISIONAL**: the 36 labels are drafts (L1) |
| Mode Q, 648 trials (36 tasks × 6 systems × 3 trials) | `experiments/results/queue/machine_A/modeq-{val,dev}-2c-2026-10-06/` | Analysis in `experiments/results/variance/`. **Calibration data, not results for claims** |
| Retrieval energy components | `experiments/results/retrieval_energy/` | — |
| Classifier before/after | `experiments/results/classifier/` | — |
| Benchmark audit | `docs/BENCHMARK_AUDIT.md` | — |

**The one finding that blocks every RQ:** correctness (plain token F1) never reaches a task
threshold (0 of 648 trials), so the primary success measure is 0 for every system (ASK_ME M1).

## Summary

| RQ | Design valid? | Sample now → planned | Main open issue | Likelihood |
|---|---|---|---|---|
| RQ1 task-aware vs fixed | Partially (M1) | 24 test → ~180 | B→C null in Mode R; correctness measure | Medium |
| RQ2 graph | Yes, after A1 | 36 dev/val | C→D null in Mode R; Mode Q needs M1 | Low–Medium |
| RQ3 verification | Yes (independent outcome) | 24 → ~180 | E refuses 21%; unsupported 81% (D 81%) | Medium |
| RQ4 routing | Yes; T1 open | 24 → ~180 | Routing tier: loops, 122 model loads | Medium |
| RQ5 strata | Partially | 4/stage → ~30/stage | Sample size | Low → Medium |
| RQ6 languages | No | Python only | Step 4 | Low |
| RQ7 fresh | No | 0 | Step 5 | Low |
| RQ8 Pareto | Yes | as RQ1 | Success undefined until M1 | Medium |

### Descriptive Mode Q on dev/val (648 trials, frozen config; not results for any claim)

| System | Token F1 | F1 ≥ threshold | Refusals | Unsupported (non-refusals) | Latency | Output tokens | GPU J/trial |
|---|---|---|---|---|---|---|---|
| A | 0.236 | 0 | 0% | 100% (cites nothing) | 13.4 s | 465 | 840 |
| B | 0.245 | 0 | 10.2% | 89.7% | 16.0 s | 358 | 849 |
| C | 0.253 | 0 | 1.9% | 85.8% | 16.2 s | 342 | 854 |
| D | 0.260 | 0 | 0% | 80.6% | 16.5 s | 315 | 848 |
| E | 0.248 | 0 | 21.3% | 81.2% | 30.0 s | 548 | 1,528 |
| E + routing | 0.235 | 0 | 21.3% | 92.9% | 31.2 s | 804 | 1,435 |

"Unsupported" means the answer cites no line inside the labelled evidence (draft labels).

**Run-to-run variance (Step 2c):**
- A–E give identical answers across 3 trials on 7–10 of 36 tasks.
- Trial-to-trial share of F1 variance is 2–10%.
- The binary outcomes agree 93–100% across trials.
- Cause: numeric-path effects (prompt cache after a model load, the output limit), not sampling
  (V1). Model reloads happen because the routing tier evicts the 7B: 7–14 per system for A–E, 122 for
  E + routing.

---

## RQ1: Does task-aware retrieval improve answer quality over fixed RAG at comparable or lower cost?

**Design valid.** Partially. Fixed in Step 2:
- The cut-off confound (D17 → C26). No system has a zero-evidence task now (C/D had 3).
- The classifier, revised on dev. All four fields right: val 1 → 2 of 12, dev 3 → 12 of 24. The dev
  gain far exceeds val's: fitting to dev.

Not valid yet: the correctness measure (M1).

**Sample size and power.** 24 test tasks give MDE ≈ 0.16 (span recall); about 180 give ≈ 0.06.

**Baselines.** A and B present.

**Confounds left.**
- **Evidence budget differs by design:** C has 6.5 text chunks per task against B's 5.0.
- **Classifier errors:** val stage agreement is 7/12.
- **M1.**

**Evidence.** Mode R B→C, span Recall@5: +0.009 (95% CI −0.07 to +0.08, p = 0.83, n = 36, provisional).
Mode Q dev/val: F1 0.245 (B) vs 0.253 (C), unsupported 89.7% vs 85.8% (descriptive, not tested; dev
is calibration data).

**Likelihood of a supported answer:** Medium. The retrieval difference is null so far; the question is
answerable once M1 is fixed.

**Smallest remaining fix.** M1, then L1 (label verification).

## RQ2: Does knowledge-graph augmentation improve multi-file and structural reasoning?

**Design valid.** Yes, after A1 (C23): D = C's retrieval + graph context, on 28 of 36 tasks (was 3).

**Sample size.** 36 dev/val; 21 multi-file.

**Baselines.** C. External Mode R sets are pending the licence audit (Step 6).

**Confounds left.** Graph chunks name files and relations, not code text.

**Evidence.**
- Mode R C→D, file Recall@10: +0.014 (CI 0.00–0.04, p = 0.32; one task changes). Graph chunks come
  after the text, so ranking metrics barely move.
- Mode Q dev/val: F1 0.253 (C) → 0.260 (D); unsupported 85.8% → 80.6%; refusals 1.9% → 0%
  (descriptive).

**Likelihood of a supported answer:** Low–Medium. Any effect must show in answers (Mode Q), not ranking.

**Smallest remaining fix.** M1; external Mode R datasets.

## RQ3: Does verification with bounded escalation reduce unsupported answers?

**Design valid.** Yes. The outcome is independent of E's gate (C22). Refusals are separate.

**Sample size.** As RQ1. Binary outcome per task: McNemar.

**Baselines.** D.

**Confounds left.**
- **Labels are drafts** (L1).
- **Test labels** are needed before the final run.

**Evidence.** Mode Q dev/val (descriptive): E's unsupported rate equals D's (81.2% vs 80.6%), while E
refuses 21.3% of tasks (D 0%) and takes about 1.8× the latency and energy. On these data, verification
converts answers into refusals rather than into better-supported answers. That is a potential negative
finding, reported as it stands.

**Likelihood of a supported answer:** Medium. Either direction is answerable.

**Smallest remaining fix.** L1; test labels.

## RQ4: Can model routing cut energy and cost while keeping per-task quality?

**Design valid.** Yes. Model loads are measured and counted (C20).

**Sample size.** As RQ1.

**Baselines.** E; large-LLM baseline open (D4).

**Confounds left.**
- **T1:** small-tier repetition loops, 9 of 108 trials.
- **Model swaps:** 122 loads in 108 trials, which also evict the 7B for the other systems.

**Evidence.** Mode Q dev/val (descriptive): E + routing uses 1,435 J vs E's 1,528 J per trial (−6%).
Unsupported rate 92.9% vs 81.2%; output 804 vs 548 tokens.

**Likelihood of a supported answer:** Medium. On these data the quality constraint looks violated: a
possible negative finding.

**Smallest remaining fix.** T1, D4, M1.

## RQ5: Does the benefit vary by SDLC stage, complexity and criticality?

**Design valid.** Partially. The method is ready (mixed model, stratified Holm).

**Sample size.** 4 per stage on test now; target about 30 per stage (Step 3).

**Baselines.** As RQ1.

**Confounds left.** 2 repositories only.

**Evidence.** None yet.

**Likelihood of a supported answer:** Low → Medium with Step 3.

**Smallest remaining fix.** Step 3 (task drafting plus review throughput, R1).

## RQ6: Does the system generalise across repositories and languages?

**Design valid.** No. Python only.

**Sample size.** 0 non-Python tasks.

**Baselines.** —

**Confounds left.** Chunker quality differs by language.

**Evidence.** None.

**Likelihood of a supported answer:** Low.

**Smallest remaining fix.** Step 4 (L6: gson and express recommended).

## RQ7: Do the results hold on fresh, contamination-controlled tasks?

**Design valid.** No. EIH-Fresh does not exist.

**Sample size.** 0.

**Baselines.** —

**Confounds left.** Model cutoff dates must be recorded.

**Evidence.** None.

**Likelihood of a supported answer:** Low.

**Smallest remaining fix.** Step 5 (F1: size).

## RQ8: What is the quality–latency–energy–cost–carbon Pareto frontier?

**Design valid.** Yes. Energy is whole-trial and MEASURED. CO₂e per success includes model loads.

**Sample size.** As RQ1.

**Baselines.** All systems; large-LLM baseline open (D4).

**Confounds left.**
- **CO₂e per success is undefined** while success is 0 everywhere (M1).
- **Non-generation GPU energy** (28–65 J/trial) includes idle draw between steps (field described so).

**Evidence.**
- Mode Q dev/val GPU J/trial: 840–1,528.
- Retrieval compute 0.3–19 J/query.

**Likelihood of a supported answer:** Medium.

**Smallest remaining fix.** M1.
