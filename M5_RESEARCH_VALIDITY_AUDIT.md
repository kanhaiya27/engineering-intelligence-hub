# Phase-2 M5: Scientific Validity & Pre-Test Integrity Audit Report

**Date**: 2026-08-20  
**Project**: Engineering Intelligence Hub (EIH)  
**Research Title**: *Task-Aware Energy-Efficient RAG for Software Engineering: Optimising Quality, Cost, Latency, Energy and Carbon Footprint*  
**Branch**: `phase-2-intelligence` | **Commit**: `35f86ba`  
**Held-Out Test Set Isolation Status**: **100% UNTOUCHED & FROZEN** (24 Tasks)  

---

## Executive Summary & Decision Gate

### **FINAL DECISION GATE RESULT**:
$$\mathbf{YELLOW \text{ — FIX SPECIFIC ISSUES BEFORE HELD-OUT TEST}}$$

**Scientific Validity Score**: **68 / 100**

While the M5 software architecture, dataset partitioning, telemetry tracking, and multi-system execution pipeline are 100% functional and hermetically tested (159/159 pytest pass), this audit identified **three P0 scientific flaws** in the quality evaluation scoring logic and mock provider calibration that would invalidate research claims if uncorrected prior to final held-out test execution.

---

## Key Audit Findings across 14 Audit Areas

### 1. Quality Evaluation Pipeline Audit
- **Correctness vs Gate Signals**: `task_correctness` against ground truth (`CorrectnessEvaluator`) was computed but **completely omitted** from `composite_quality` in `experiments/m5/runner.py`. `composite_quality` was calculated solely from 4 quality gate signals:
  $$\text{composite\_q} = 0.35 S_{\text{citation}} + 0.25 S_{\text{relevance}} + 0.20 S_{\text{coverage}} + 0.20 S_{\text{consistency}}$$
- **Dependency Flow**: Evaluators evaluated candidate text, but formatting penalties (e.g. missing `[file.py:L10]` brackets) artificially depressed scores to 0.30 even for correct answers.

```
Task (Query, Ground Truth)
  │
  ├─► System A/B/C/D/E Pipeline ─► Answer Text + Chunks
  │                                    │
  │                                    ├─► QualityGate (Citation, Relevance, Coverage, Consistency) ─► composite_q
  │                                    │                                                                   │
  └────────────────────────────────────┴─► CorrectnessEvaluator (F1 Ground Truth) ─► task_correctness     ▼
                                            (OMITTED FROM COMPOSITE QUALITY!)                       QC Success
```

---

### 2. Investigation of Identical Quality Scores (0.5033)
- **Root Cause**: `MockLLMProvider` generates static canned text strings (`SUPPORTED BY EVIDENCE: In Flask, routing is handled...`) for all Flask queries regardless of retrieved chunks.
- **Impact**: Baselines A, B, System C, and System D generated identical answer text for all Flask tasks during mock Dev runs, causing identical evaluator scores ($0.5033$).
- **Classification**: **PIPELINE VALIDATION ARTIFACT — NOT RESEARCH EVIDENCE**.

---

### 3. Investigation of System E (0.9625 Quality / 100% QC Success)
- **Root Cause**: When System E exhausted 3 retrieval attempts with `MockLLMProvider`, it constructed a fallback refusal answer starting with `"INSUFFICIENT EVIDENCE"`.
- **Evaluator Flaw**: `verification/evaluators.py` awarded `"INSUFFICIENT EVIDENCE"` refusals full scores ($1.0$ on Citation, $1.0$ on Coverage, $1.0$ on Consistency, $0.85$ on Relevance), resulting in $\text{composite\_q} = 0.9625$.
- **Impact**: System E was classified as 100% Quality-Constrained Successful **for refusing to answer tasks requiring engineering answers**.
- **Remediation**: Refusals must receive neutral/capped quality credit ($0.50$) and MUST NOT count as successful task completions for tasks with known ground truth answers.

---

### 4. Mock LLM Provider Assessment
- `MockLLMProvider` is deterministic and fast (10ms), suitable ONLY for hermetic unit testing (`pytest`).
- **Recommendation**: Research calibration and final Held-Out Test evaluation MUST use live `OpenAIProvider` (`gpt-4o-mini`).

---

### 5. Retrieval Differentiation Audit
- Chunks, strategies, and hop depths differ significantly across Systems B, C, D, and E in `retrieval.chunks`.
- Differentiation will fully manifest downstream when live LLM generation is enabled.

---

### 6. Failure Taxonomy Audit
- `diagnose_trial_failure` in `experiments/m5/failure_tax.py` is an empirical rule engine.
- When fed 0-chunk mock telemetry, it categorized failures as `RETRIEVAL_MISS`.
- Taxonomy rules are sound and ready for live trial telemetry.

---

### 7. Sustainability & Energy Measurements
- NVML GPU power is directly `MEASURED` during GPU inference.
- CPU energy, API cost, and grid carbon are accurately `ESTIMATED`.
- **Recommendation**: Increase trials from $N=3$ to $N=5$ for the final Held-Out Test run to reduce live API latency variance.

---

### 8. Validation Candidate Selection Audit
- Candidate 2 (`top_k=4, hop_depth=1`) was selected on mock data ($0.2444\text{ J}$).
- Difference ($0.0252\text{ J}$) is within measurement noise on mock latency.
- Candidate parameters must be re-calibrated on live Validation runs.

---

### 9. Ablation Claims Audit
- $A\to B \to C \to D$ quality deltas ($+0.0000$) and $D\to E$ jump ($+0.4592$) are mock artifacts.
- Explicitly labeled as **PRELIMINARY PIPELINE VALIDATION ONLY**.

---

### 10. Dataset & Split Integrity
- `splits_v1.0.json`: 24 Dev, 12 Val, 24 Test (Seed 42).
- **Held-Out Test Set (24 tasks) was 100% untouched.** Zero task IDs or contents influenced classifier or retriever tuning.

---

### 11. NVIDIA Technology & Hardware Integration
- NVIDIA RTX 4050 Laptop GPU, PyTorch CUDA 2.6.0, and NVML telemetry (`pynvml`) are fully operational.
- Architecture remains vendor-neutral for high scientific generalizability.

---

## Remediation Plan (P0 / P1 / P2)

### P0 Actions (Must Fix Before Held-Out Test Execution):
1. **P0-1: Incorporate Factual Correctness into Composite Quality**:
   Update composite quality formula in `experiments/m5/runner.py`:
   $$\text{composite\_q} = 0.40 S_{\text{correctness}} + 0.25 S_{\text{citation}} + 0.15 S_{\text{relevance}} + 0.10 S_{\text{coverage}} + 0.10 S_{\text{consistency}}$$
2. **P0-2: Cap Refusal Quality Credit**:
   Modify `verification/evaluators.py` so `"INSUFFICIENT EVIDENCE"` refusals receive a maximum score of $0.50$, preventing false 100% QC success.
3. **P0-3: Re-Run Calibration with Live `gpt-4o-mini`**:
   Execute parameter calibration on the 12 Validation tasks using live LLM generation before freezing the final manifest.

### P1 Actions (Strongly Recommended):
1. **P1-1: Increase Test Repetitions to $N=5$**: Set $N=5$ repeated trials for final Test evaluation.

---

## Required Conditions Before Running Held-Out Test

1. Apply P0-1, P0-2, and P0-3 remediations.
2. Verify all 159+ pytest suite tests pass.
3. Re-freeze `experiments/results/m5/frozen/final_experiment_manifest.json`.
4. Execute final test run command:
   ```powershell
   .venv311\Scripts\python.exe -m experiments.m5.runner --split test --trials 5 --manifest experiments/results/m5/frozen/final_experiment_manifest.json
   ```
