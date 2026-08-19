# Evaluation Framework & Baseline Experiments

## Overview

The evaluation framework executes experimental pipelines against the benchmark suite, collects quality and sustainability telemetry, and logs reproducible events to structured JSONL logs.

---

## 1. Experimental Baselines

### Baseline A: LLM-Only (`BaselineARunner`)
- **Mode**: Zero retrieval context (`skip_retrieval=True`).
- **Purpose**: Establishes the lower performance bound for factual grounding, hallucinations, and ungrounded software advice.
- **Log Location**: `experiments/results/<experiment_id>/events.jsonl`

### Baseline B: Fixed RAG + Fixed Model (`BaselineBRunner`)
- **Mode**: Standard Hybrid Retrieval ($w_{\text{dense}}=0.7, w_{\text{sparse}}=0.3, k=5$).
- **Purpose**: Establishes the non-adaptive RAG baseline against which future task-aware adaptive routing policies (Phase 2+) will be benchmarked.

---

## 2. Evaluation Scorers (`evaluation/scorers/`)

### Correctness (`CorrectnessEvaluator`)
- Compares generated answer against `ground_truth` and `acceptable_alternatives`.
- Computes token overlap F1 score normalized to $[0.0, 1.0]$.

### Groundedness (`GroundednessEvaluator`)
- Evaluates whether claims in generated answers are grounded in retrieved chunks.
- Checks presence of verifiable source citations (`[file:lines]`).
- Rewards `SUPPORTED BY EVIDENCE` and valid refusal on missing facts (`INSUFFICIENT EVIDENCE`).

### Relevance (`RelevanceEvaluator`)
- Computes query-answer keyword coverage and semantic alignment.

---

## 3. Metrics Schema

All task evaluations generate an `ExperimentResult` containing:
- `QualityMetrics`: `task_correctness`, `groundedness`, `relevance`, `aggregated_quality_score`, `passed_quality_gate`.
- `EfficiencyMetrics`: `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`, `energy_joules`, `co2e_grams`.
- `EngineeringOutcomeMetrics`: `task_completed`, `rework_proxy_score`.
