# RQ readiness

Updated after Step 1 (5 Oct 2026, branch `master-fix`). One entry per research question
(`docs/original_plan.md` §3). The original plan states no formal hypotheses beyond RQ1–RQ8 and
contributions C1–C4.

**Evidence so far:**
- Mode R on the 36 dev/val tasks (`experiments/results/mode_r/machine_A/mode-r-devval-2026-10-05/`).
  It is **provisional**: all 36 labels are still `draft` until Avaneesh verifies them (ASK_ME L1).
- Retrieval energy by component (`experiments/results/retrieval_energy/machine_A/retrieval-energy-2026-10-05/`).
- Per-call model energy from Phase 1.

**No Mode Q (answer) results exist yet.** Real Mode Q runs are blocked until ASK_ME A3 (2 stray test
nodes in the live graph) is resolved.

**Power figures.** These are minimum detectable effects (MDE), two-sided α = 0.05, power 0.80, paired
Wilcoxon. They use the per-task standard deviation of differences observed in Mode R as a stand-in for
answer-level variation, which is not yet measured. Example: span Recall@5, B vs C, SD 0.27 →

| Tasks | MDE |
|---|---|
| 24 (current test split) | 0.16 |
| 30 (one stratum) | 0.14 |
| 36 | 0.13 |
| 180 (test split at ~450 tasks) | 0.06 |

## Summary

| RQ | Design valid? | Sample now → planned | Baselines | Likelihood |
|---|---|---|---|---|
| RQ1 task-aware vs fixed | Partially | 24 test → ~180 | B present | Medium |
| RQ2 graph | **No, until A1** | 36 dev/val (3 with graph) | C present | Low |
| RQ3 verification | Yes, after Step 1f | 24 → ~180 | D present | Medium |
| RQ4 routing | Yes | 24 → ~180 | E present; large-LLM baseline open (D4) | Medium |
| RQ5 by stage/complexity/criticality | Partially | 4 per stage → ~30 per stage | — | Low → Medium |
| RQ6 repos/languages | No | Python only | — | Low |
| RQ7 fresh tasks | No | 0 | — | Low |
| RQ8 Pareto | Yes, after 1b/1h | as RQ1 | all systems | Medium |

---

## RQ1: Does task-aware retrieval improve answer quality over fixed RAG at comparable or lower cost?

**Design valid.** Partially.
- Valid: C differs from B only by task classification plus the adaptive strategy (one fixed config,
  `configs/inference.yaml`).
- Not yet valid: correctness was lexical F1 inflated ×1.5. That is fixed (C19). It is not yet
  checked against human ratings (1e tooling ready). The success definition still leans on E's gate
  signals (ASK_ME A2).

**Sample size and power.** 24 test tasks give MDE ≈ 0.16 (span recall); about 180 give ≈ 0.06. In
Mode R, B→C is +0.005 span Recall@5 (95% CI −0.08 to +0.09, p = 0.85, n = 36). That is no detectable
retrieval difference at this n.

**Baselines present.** A (LLM only) and B (fixed hybrid). Yes.

**Confounds left.**
- **Score thresholds (D17).** C and D retrieve nothing on 3 of 36 tasks (dev-026, rev-048, test-032);
  B has no threshold. Mode R table "Zero-evidence tasks". Step 2b.
- **Classifier accuracy is unmeasured** beyond 4 tasks (Step 2a).
- **Run-to-run variation at temperature 0** (D16; also B req-010: 981 vs 853 tokens). Step 2c.

**Evidence.**
- `experiments/results/mode_r/machine_A/mode-r-devval-2026-10-05/report.md`: B vs C file and span metrics.
- `experiments/stats.py` (paired tests, Holm), `experiments/m5/analysis.py` (`co2e_per_successful_task`).

**Likelihood of a supported answer:** Medium. The machinery is now valid, but the retrieval difference
B→C is ~0 at n = 36. A quality gain would have to come from the strategy's context size, not from
better ranking.

**Smallest remaining fix.**
- Steps 2a–2c.
- Decide A2.
- Rate 30–50 answers to validate the correctness F1.

## RQ2: Does knowledge-graph augmentation improve multi-file and structural reasoning?

**Design valid. No, as built.** D adds graph context only when the adaptive policy picks a graph
strategy: 3 of 36 dev/val tasks. On the other 33, D's retrieval is identical to C's. Mode R:
- C→D file Recall@5 difference is exactly 0, on every task.
- Graph chunks appear on 3 tasks for D.
- They appear on 35–36 tasks for E's rungs 2 and 3.

**Sample size and power.** As built, Δ(C→D) rests on 3 tasks: no power. With A1(b) (graph on every
task) it rests on all tasks; 21 of 36 dev/val labels are multi-file.

**Baselines present.** C. External Mode R sets (CrossCodeEval, RepoBench) are not yet licensed
(Step 6).

**Confounds left.**
- **Graph chunks carry no source text.** They name files and relations, so they help at file level
  only. Both levels are reported (`evaluation/retrieval_metrics.py`).
- **Graph contamination.** Two stray test nodes are in the live graph (A3). They don't affect
  retrieval, but they block real runs.

**Evidence.**
- Mode R report and `metrics.json` (`n_graph_chunks` per task).
- `experiments/results/graph_build/machine_A/graph_build_wave1.json`.

**Likelihood of a supported answer:** Low until A1 is decided. Medium with A1(b) plus the external
Mode R sets.

**Smallest remaining fix.** Decide A1 (recommended: D = C + graph on every task), then re-run Mode R.
That takes about 1 GPU-minute.

## RQ3: Does quality-aware verification with bounded escalation reduce unsupported answers?

**Design valid.** Yes, after Step 1f. The outcome is now independent of E's gate. Cited line spans are
checked against the human-checked evidence spans (`evaluation/outcome.py`). The outcomes are:
- unsupported-answer rate over non-refusals;
- refusal rate, separately;
- cited-span precision and recall.

E's own evaluators remain only as gate signals.

**Sample size and power.** As RQ1. The unsupported rate is a paired binary outcome per task, tested with
`mcnemar_exact`.

**Baselines present.** D (same retrieval as E's attempt 0).

**Confounds left.**
- **Labels needed for every test task** before the final run (decided: labelled right before it).
- **The consistency evaluator is weak** (`docs/PROJECT_REPORT.md:708`). It is a gate signal, no longer
  the outcome.

**Evidence.**
- Mode R: E's escalation rungs widen retrieval. Span Recall@10 rises from 0.37 (D) to 0.54
  (rung 3, esc_max): +0.17, 95% CI 0.08–0.29, p = 0.004, n = 36, draft labels. This is retrieval
  only. Whether E reaches those rungs depends on its gate, which only Mode Q shows.
- `evaluation/outcome.py`, `tests/test_evaluation/test_outcome.py`.

**Likelihood of a supported answer:** Medium. Escalation demonstrably retrieves more of the labelled
evidence; whether answers become better supported is unmeasured.

**Smallest remaining fix.** Mode Q dev/val (Step 7a) after A3. Test labels before the final run.

## RQ4: Can task-aware model routing reduce energy and cost while keeping per-task quality?

**Design valid.** Yes. E→E_routed adds exactly one capability (`system_e_routed`).
- Model reload energy is now MEASURED per trial (`model_load_energy_joules`) and included in CO₂e per
  successful task (Step 1b).
- Whole-trial GPU energy is now measured (Step 1h, C20).

**Sample size and power.** As RQ1. Big-Vul/PrimeVul (1,000) would add power for the criticality
question, but they are not licensed yet and the GPU budget is open (G1).

**Baselines present.** E (fixed 7B). Large-LLM baseline open (D4).

**Confounds left.**
- **Routing depends on classifier accuracy** (Step 2a).
- **Run-to-run variance** (Step 2c).

**Evidence.**
- Phase-1 per-call energy at 12K context: 1.5B 348.6 J, 3B 478.4 J
  (`experiments/results/phase1/machine_A/ctx12k_small_models/long_context_probe.md:7-8`);
  7B 762.8 J (`long_context_probe.md:9`).

**Likelihood of a supported answer:** Medium.

**Smallest remaining fix.** Step 2a; decide D4; Mode Q.

## RQ5: Does the benefit vary by SDLC stage, complexity and criticality?

**Design valid.** Partially. Now available:
- the interaction test (`experiments/stats.py` `mixed_effects`, Wald test of system × stratum);
- per-stratum paired tests with Holm.

**Sample size and power.** 4 test tasks per stage now: no power (MDE > 0.3). The target is about 30 per
stage per stratum (Step 3a), giving MDE ≈ 0.14 per stratum.

**Baselines present.** Same as RQ1.

**Confounds left.**
- **Two repositories only** in the current benchmark.
- **Stage and repository are partly confounded** until the six repos are covered.

**Evidence.** `tests/test_experiments/test_stats.py::test_stratified_and_mixed_effects_detect_interaction`
(method check on synthetic data, not a result).

**Likelihood of a supported answer:** Low now. Medium if ~450 tasks are approved by 12 Oct (review
shortfall: ASK_ME R1).

**Smallest remaining fix.** The task-drafting tool (3a) and review throughput (R1).

## RQ6: Does the system generalise across repositories and programming languages?

**Design valid.** No. The corpus is Python only and tree-sitter is not installed.

**Sample size.** 0 non-Python tasks.

**Baselines.** —

**Confounds left.** Chunker quality versus language (plan §12). Requires AST-aware chunking per
language.

**Evidence.** `datasets/registry.yaml` (waves 3–4 name the Java, JS, Go, Rust and C/C++ repositories).

**Likelihood of a supported answer:** Low.

**Smallest remaining fix.**
- Step 4: tree-sitter plus 2 repositories (recommended gson and express, ASK_ME L6).
- Their graph and about 60 reviewed tasks.

## RQ7: Do the results hold on fresh, contamination-controlled tasks?

**Design valid.** No. EIH-Fresh does not exist.

**Sample size.** 0. The planned size is 50 or ~150 (ASK_ME F1).

**Baselines.** —

**Confounds left.** Model cutoff dates must be recorded (spec §6.1).

**Evidence.** None.

**Likelihood of a supported answer:** Low.

**Smallest remaining fix.** Step 5: post-cutoff repositories, frozen by hash before any run.

## RQ8: What is the quality–latency–energy–cost–carbon Pareto frontier?

**Design valid.** Yes, after Steps 1b and 1h.
- Energy is now whole-pipeline (retrieval included, measured per trial).
- CO₂e per successful task is implemented, including model loads.
- Latency is decomposed per trial.

**Sample size.** As RQ1.

**Baselines.** All systems; large-LLM baseline open (D4).

**Confounds left.**
- **Single GPU** (absolute joules are hardware-specific; plan §12).
- **CO₂e and cost are ESTIMATED** by design (plan §9.1).

**Evidence.** Retrieval energy per query, net of idle GPU power (4.26 W). Measured 5 Oct, 36 dev/val
queries × 5 repeats per counter-only window
(`experiments/results/retrieval_energy/machine_A/retrieval-energy-2026-10-05/report.md`).

| Component or system | Net GPU energy per query [MEASURED − idle] |
|---|---|
| Embedding | 0.39 J |
| Cross-encoder over 30 candidates | 8.72 J |
| Graph increment | 0.56 J |
| B | 0.27 J |
| C | 3.07 J |
| D | 3.15 J |
| E rung 1 | 4.23 J |
| E rung 2 | 5.90 J |
| E rung 3 | 18.87 J |

- CPU energy is ESTIMATED at 3.3–7.3 J per query.
- BM25 is CPU-bound. Its net GPU figure is −0.37 J/query: the GPU drew slightly less than the idle
  baseline. That is zero within noise.
- The old single-sample reranker figure (0.07–0.13 J, report §10.4) was for a few candidates. Over
  30 candidates the reranker is the largest retrieval cost.
- Retrieval is small next to generation (smoke trials: 338–2,523 J per trial), so the frontier is
  driven by generation length and escalation.

**Likelihood of a supported answer:** Medium. A frontier can always be drawn; it is now measured on the
right boundary.

**Smallest remaining fix.** Mode Q runs.
