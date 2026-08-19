# EXPERIMENT PLAN

Engineering Intelligence Hub — Experiment Design

**Status:** Draft — subject to revision as implementation progresses.

---

## Experimental Design Overview

All experiments follow a common structure:
1. Load benchmark tasks (filtered by SDLC stage, task type, split).
2. Execute the pipeline configuration defined in the experiment config.
3. Log every call to `experiments/results/<experiment_id>/events.jsonl`.
4. Compute quality and efficiency metrics.
5. Store `ExperimentResult` per task.

---

## Named Baselines and Experiments

### Baseline A — LLM Only (No RAG)
**Config:** `experiments/baselines/baseline_a.yaml`

- No retrieval
- Fixed model: gpt-4o-mini
- No quality gate
- No routing

**Purpose:** Quantify the contribution of retrieval. Compare against all other configs.

---

### Baseline B — Fixed RAG + Fixed Model
**Config:** `experiments/baselines/baseline_b.yaml` (Phase-1)

- Fixed retrieval: `dense` strategy, top_k=5
- Fixed model: gpt-4o-mini
- No quality gate, no routing, no reranking

**Purpose:** Quantify the contribution of adaptive elements. Isolates retrieval effect.

---

### Baseline C — Hybrid RAG + Fixed Model
**Config:** `experiments/baselines/baseline_c.yaml` (Phase-1)

- Fixed retrieval: `hybrid` strategy, top_k=7
- Fixed model: gpt-4o-mini
- No quality gate, no routing

**Purpose:** Isolate hybrid retrieval vs. dense-only. Quantify BM25 contribution.

---

### Experiment D — Adaptive Retrieval
**Config:** `experiments/configs/experiment_d.yaml` (Phase-2)

- Adaptive retrieval: task-type driven strategy selection
- Fixed model: gpt-4o-mini
- No quality gate, no routing

**Purpose:** Quantify the contribution of retrieval adaptation alone.

---

### Experiment E — Adaptive Retrieval + Model Routing
**Config:** `experiments/configs/experiment_e.yaml` (Phase-2)

- Adaptive retrieval: task-type driven
- Adaptive model: tier-based routing (SMALL → escalate to MEDIUM if needed)
- No quality gate

**Purpose:** Quantify joint contribution of retrieval + routing adaptation.

---

### Experiment F — Full Pipeline (Adaptive + Quality Gate)
**Config:** `experiments/configs/experiment_f.yaml` (Phase-2)

- Adaptive retrieval
- Adaptive model routing
- Quality gate active (threshold per task type)
- Escalation: up to 2 rounds

**Purpose:** Full system evaluation. Primary comparison against baselines.

---

### Advanced — Graph Augmented + Agent Orchestration
**Config:** `experiments/configs/advanced.yaml` (Phase-3/4)

- Graph-augmented retrieval
- Adaptive routing
- Quality gate
- Agent orchestration for complex multi-step tasks

---

## Ablation Study Matrix

Each ablation disables one component of Experiment F:

| Ablation | Component Disabled |
|---|---|
| ABL-01 | Adaptive retrieval → fixed `hybrid` strategy |
| ABL-02 | Model routing → fixed gpt-4o-mini |
| ABL-03 | Quality gate → no escalation |
| ABL-04 | Graph retrieval → no graph context |
| ABL-05 | Reranking → disable reranker |
| ABL-06 | Quality threshold variation → 0.60, 0.70, 0.75, 0.80, 0.85 |
| ABL-07 | Task criticality variation → LOW vs HIGH tasks only |

---

## Metrics to Collect

### Quality
- Task correctness (vs. ground truth)
- Groundedness
- Relevance
- Code compilation success (for code generation tasks)
- Test execution success (for test generation tasks)
- Aggregated quality score

### Efficiency
- End-to-end latency (ms)
- Input tokens, output tokens
- Estimated cost (USD)
- Estimated energy (joules) — method flagged
- Estimated CO₂e (grams)
- Retrieval latency (ms)
- Number of retrieved chunks

### Engineering Outcome
- Task completion rate
- Number of escalations
- Number of retries
- Rework proxy score

### Proposed Research Metrics
- Energy per Successful Engineering Task
- CO₂e per Successful Engineering Task
- Quality-Constrained Energy Efficiency

---

## Statistical Analysis Plan

- Report mean ± standard deviation (multiple runs with different seeds for variance)
- Pareto frontier plots: quality vs. energy, quality vs. cost, quality vs. latency
- Per-SDLC-stage breakdown
- Per-task-type breakdown
- Per-model breakdown
- Wilcoxon signed-rank test for statistical significance between configurations

---

## Reproducibility Requirements

Every experiment must record:
- `git_commit_sha` of codebase
- Full `ExperimentConfig` as `config.json`
- All random seeds
- Model IDs and versions
- Carbon intensity value and region used
- Hardware: CPU, GPU, VRAM, RAM
- Python version and key dependency versions

---

## Timeline

| Phase | Experiment | Target |
|---|---|---|
| Phase-1 | Baseline A | September 2026 |
| Phase-1 | Baseline B, C | September 2026 |
| Phase-2 | Experiments D, E, F | October 2026 |
| Phase-2 | Ablations ABL-01 to 07 | October 2026 |
| Phase-3 | Advanced (graph + agents) | November 2026 |
