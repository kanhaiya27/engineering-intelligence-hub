# Phase-2 M5: Controlled Evaluation Calibration & Validation Report

**Generated**: 2026-08-19 20:06:44 UTC  
**Frozen Benchmark Version**: `v1.0-phase1-60`  
**Frozen Manifest Fingerprint**: `1220f37d2798c4cf`  
**Split Counts**: Dev = 24 tasks | Validation = 12 tasks | Held-Out Test = 24 tasks (FROZEN)

> [!IMPORTANT]
> **Research Protocol Constraint Compliance**:
> - The **Held-Out Test Set (24 tasks)** was **NOT** executed, inspected, or utilized during this calibration.
> - All parameter choices were derived strictly from the **Validation Set (12 tasks)**.
> - All findings presented below are **preliminary development/validation results**.

---

## 1. Development Experiment Performance (24 Tasks x 5 Systems x 3 Trials = 360 Runs)

| System Configuration | Quality (0–1) | QC Success Rate | Latency (ms) | Total Energy (J) | Cost ($) | CO2e (g) | Quality / Joule |
|---|---|---|---|---|---|---|---|
| `baseline_a` | 0.5033 ± 0.0283 | 0.0% | 10.5 ± 0.1 | 0.3919 ± 0.2453 | $0.000030 | 0.000025 | 4.6167 |
| `baseline_b` | 0.5033 ± 0.0283 | 0.0% | 162.4 ± 586.7 | 0.1313 ± 0.2947 | $0.000029 | 0.000008 | 10.0006 |
| `system_c` | 0.5033 ± 0.0283 | 0.0% | 125.5 ± 411.9 | 0.0868 ± 0.0292 | $0.000029 | 0.000006 | 8.5299 |
| `system_d` | 0.5033 ± 0.0283 | 0.0% | 51.1 ± 5.5 | 0.1111 ± 0.0309 | $0.000029 | 0.000007 | 5.4425 |
| `system_e` | 0.9625 ± 0.0000 | 100.0% | 152.3 ± 10.8 | 0.3375 ± 0.0824 | $0.000089 | 0.000022 | 3.2134 |

---

## 2. Preliminary Stepwise Ablation Deltas (Development Split)

| Transition | Delta Quality | Delta QC Success | Delta Latency (ms) | Delta Energy (J) | Delta Cost ($) | Delta CO2e (g) |
|---|---|---|---|---|---|---|
| **A -> B (Add Fixed RAG)** | +0.0000 | — | +151.9 | -0.2606 | -0.000001 | -0.000017 |
| **B -> C (Add Task-Aware Adaptive)** | +0.0000 | — | -37.0 | -0.0445 | +0.000000 | -0.000002 |
| **C -> D (Add Knowledge Graph)** | +0.0000 | — | -74.4 | +0.0243 | +0.000000 | +0.000001 |
| **D -> E (Add Quality Gate & Escalation)** | +0.4592 | — | +101.2 | +0.2264 | +0.000060 | +0.000015 |

---

## 3. Validation Calibration & Parameter Selection (12 Tasks x 4 Candidates)

**Winning Configuration**: `Candidate 2: Focused Context (Low Footprint)` (`cand_2_focused_context`)

**Selection Rationale**: Selected 'Candidate 2: Focused Context (Low Footprint)' because it achieved the highest Quality-Constrained Success Rate (100.0%) with Composite Quality = 0.9625 and Energy = 0.2444 J.

| Candidate ID | Parameters | System E QC Success | System E Quality | System E Energy (J) | Selection Status |
|---|---|---|---|---|---|
| `cand_1_baseline_heuristic` | top_k=5, hop_depth=2, max_esc=2 | 100.0% | 0.9625 | 0.2696 J | Alternative |
| `cand_2_focused_context` | top_k=4, hop_depth=1, max_esc=2 | 100.0% | 0.9625 | 0.2444 J | ⭐ **SELECTED** |
| `cand_3_expanded_context` | top_k=6, hop_depth=2, max_esc=2 | 100.0% | 0.9625 | 0.4197 J | Alternative |
| `cand_4_conservative_escalation` | top_k=5, hop_depth=2, max_esc=3 | 100.0% | 0.9625 | 0.2992 J | Alternative |

---

## 4. Failure Mode Taxonomy Summary (13 Standard Categories)

| System ID | Total Diagnoses | Top Failure Mode | Primary Failure Counts |
|---|---|---|---|
| `baseline_a` | 216 | `unsupported_citation` | unsupported_citation: 105, no_failure: 72, irrelevant_evidence: 39 |
| `baseline_b` | 216 | `retrieval_miss` | retrieval_miss: 216 |
| `system_c` | 216 | `retrieval_miss` | retrieval_miss: 216 |
| `system_d` | 216 | `retrieval_miss` | retrieval_miss: 216 |
| `system_e` | 216 | `retrieval_miss` | retrieval_miss: 216 |

---

## 5. Frozen Test Execution Command

To execute the final benchmark evaluation on the **Held-Out Test Set (24 tasks x 5 systems x 3 trials)**:

```powershell
.venv311\Scripts\python.exe -m experiments.m5.runner --split test --trials 3 --manifest experiments/results/m5/frozen/final_experiment_manifest.json
```