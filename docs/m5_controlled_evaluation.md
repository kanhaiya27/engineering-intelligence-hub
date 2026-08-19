# Phase-2 M5: Controlled Evaluation Framework Specification

## 1. Overview & Research Objective

**Research Title**: *Task-Aware Energy-Efficient RAG for Software Engineering: Optimising Quality, Cost, Latency, Energy and Carbon Footprint*

Phase-2 Milestone 5 establishes a formal, reproducible, and vendor-neutral evaluation framework to compare conventional Fixed RAG with Task-Aware Adaptive RAG, Knowledge Graph Augmentation, and Quality-Aware Verification.

---

## 2. The Five Systems Under Comparison

```
+---------------------------------------------------------------------------------------------------+
| BASELINE A: LLM-Only                                                                              |
| Query → LLM Generation → Response (No retrieval, No graph, No quality gate)                       |
+---------------------------------------------------------------------------------------------------+
| BASELINE B: Fixed Hybrid RAG                                                                      |
| Query → Fixed Hybrid Retrieval (Dense 0.70 / BM25 0.30, top_k=5) → Generation → Response           |
+---------------------------------------------------------------------------------------------------+
| SYSTEM C: Task-Aware Adaptive RAG                                                                 |
| Query → M1 Task Classification → M3 Adaptive Retrieval Policy → Generation → Response              |
+---------------------------------------------------------------------------------------------------+
| SYSTEM D: Task-Aware + Knowledge Graph RAG                                                        |
| Query → M1 Classification → M3 Adaptive Policy + M2 AST Knowledge Graph → Generation → Response   |
+---------------------------------------------------------------------------------------------------+
| SYSTEM E: Full Proposed System                                                                    |
| Query → M1 Classification → M3 Adaptive + M2 Graph → Generation → M4 Quality Gate → Bounded Esc.   |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Dataset Splitting Protocol & Provenance

The 60 benchmark tasks in `benchmark/data/meib_phase1_tasks.json` (`v1.0-phase1-60`) are partitioned into 3 deterministic, stratified splits with **Seed = 42** in `benchmark/data/splits_v1.0.json`:

- **Development Set (Dev)**: 24 tasks ($40\%$) — 4 per SDLC stage (2 Flask, 2 FastAPI). Used for tuning retrieval weights, top-k deltas, and debugging.
- **Validation Set (Val)**: 12 tasks ($20\%$) — 2 per SDLC stage (1 Flask, 1 FastAPI). Used for selecting policy candidates and escalation ceilings.
- **Held-Out Test Set (Test)**: 24 tasks ($40\%$) — 4 per SDLC stage (2 Flask, 2 FastAPI). **Frozen for final evaluation only; zero parameter tuning permitted.**

### Stratification Matrix
$$\begin{array}{l|cc|c}
\textbf{SDLC Stage} & \textbf{pallets/flask} & \textbf{fastapi/fastapi} & \textbf{Split Allocations (Dev / Val / Test)} \\
\hline
\text{Requirements} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\text{Architecture} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\text{Development} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\text{Testing} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\text{Code Review} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\text{Maintenance} & 5 & 5 & 4 \text{ Dev} / 2 \text{ Val} / 4 \text{ Test} \\
\hline
\textbf{Total} & 30 & 30 & \mathbf{24\text{ Dev} / 12\text{ Val} / 24\text{ Test}}
\end{array}$$

---

## 4. Metric Classification & Provenance

Every metric collected by `experiments/m5/metrics.py` is categorized under a strict 3-tier provenance model:

| Metric | Category | Instrument / Formula | Unit |
|---|---|---|---|
| `latency_ms` | **MEASURED** | Direct `time.perf_counter()` timer | $\text{ms}$ |
| `retrieval_latency_ms` | **MEASURED** | Retriever component timer | $\text{ms}$ |
| `generation_latency_ms` | **MEASURED** | LLM provider component timer | $\text{ms}$ |
| `input_tokens`, `output_tokens` | **MEASURED** | Tokenizer / Provider token counter | $\text{tokens}$ |
| `gpu_energy_measured_joules` | **MEASURED** | NVML hardware power sensor integration | $\text{Joules}$ |
| `chunks_retrieved_count` | **MEASURED** | Length of retrieved context chunks | $\text{chunks}$ |
| `graph_chunks_count` | **MEASURED** | Graph context chunks injected | $\text{chunks}$ |
| `escalation_count` | **MEASURED** | Number of retrieval escalation steps | $\text{count}$ |
| `cpu_energy_joules` | **ESTIMATED** | $\text{TDP}_{\text{cpu}} \times (\text{latency\_ms} / 1000)$ | $\text{Joules}$ |
| `total_energy_joules` | **ESTIMATED** | $\text{Energy}_{\text{cpu}} + \text{Energy}_{\text{gpu}}$ | $\text{Joules}$ |
| `cost_usd` | **ESTIMATED** | $N_{\text{in}} \times \$0.15/\text{1M} + N_{\text{out}} \times \$0.60/\text{1M}$ | $\text{USD}$ |
| `co2e_grams` | **ESTIMATED** | $(\text{TotalEnergy} / 3.6\times 10^6) \times 233.0\text{ gCO}_2/\text{kWh}$ | $\text{gCO}_2\text{e}$ |
| `composite_quality` | **DERIVED** | $0.35 S_{\text{cit}} + 0.25 S_{\text{rel}} + 0.20 S_{\text{cov}} + 0.20 S_{\text{con}}$ | $[0.0, 1.0]$ |
| `quality_per_joule` | **DERIVED** | $\text{composite\_quality} / \text{total\_energy\_joules}$ | $\text{pts/J}$ |
| `quality_per_dollar` | **DERIVED** | $\text{composite\_quality} / \text{cost\_usd}$ | $\text{pts/\$}$ |
| `quality_constrained_success` | **DERIVED** | $\text{composite\_quality} \ge \text{quality\_threshold}$ | $\text{Boolean}$ |

### Quality-Constrained Efficiency Rule
A system is energy/cost efficient on a task **if and only if**:
$$\text{composite\_quality} \ge \text{task\_quality\_threshold}$$
If a system reduces resource consumption but produces an unverified or low-quality answer, the trial is flagged as `INVALID SAVING / QUALITY FAILURE`.

---

## 5. Ablation Transitions & Pareto Frontiers

### Stepwise Ablations
1. $\Delta(A \to B)$: Marginal impact of adding basic fixed RAG retrieval.
2. $\Delta(B \to C)$: Marginal impact of task-aware dynamic retrieval routing.
3. $\Delta(C \to D)$: Marginal impact of AST knowledge graph context injection.
4. $\Delta(D \to E)$: Marginal impact of 4-signal quality gate and bounded escalation ladder.

### 2D Pareto Frontiers
Non-dominated solutions are identified where no other configuration achieves strictly higher quality at strictly lower resource cost:
- Quality vs Total Energy (J)
- Quality vs Cost (USD)
- Quality vs Latency (ms)
- Quality vs Carbon (gCO2e)

---

## 6. Failure Taxonomy & Human Evaluation Protocol

### 13 Standard Failure Categories
`RETRIEVAL_MISS`, `GRAPH_MISS`, `IRRELEVANT_EVIDENCE`, `UNSUPPORTED_CITATION`, `HALLUCINATION`, `QUALITY_GATE_FALSE_POSITIVE`, `QUALITY_GATE_FALSE_NEGATIVE`, `UNNECESSARY_ESCALATION`, `EXCESSIVE_LATENCY`, `EXCESSIVE_ENERGY`, `EXCESSIVE_COST`, `PARSER_FAILURE`, `API_FAILURE`.

### Human Validation Rubric
12-task stratified sample annotated on a 1–5 scale across Correctness, Groundedness, Relevance, Evidence Completeness, and Actionability to calibrate automated scoring signals.
