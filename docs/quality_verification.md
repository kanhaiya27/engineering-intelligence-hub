# Engineering Intelligence Hub — Quality-Aware Verification Architecture

## Overview

The **Quality-Aware Verification Layer** (Phase-2 Milestone 4) guarantees evidence-grounded responses and prevents hallucinations in software engineering tasks. It operates as an automated quality gate between LLM generation and user delivery.

```
EngTaskRequest + Retrieved Evidence Chunks
               ↓
        LLM Generation
               ↓
       Candidate Response
               ↓
   Quality Gate Verification
   ├── 1. Citation Grounding Evaluator   (w=0.35)
   ├── 2. Query Relevance Evaluator      (w=0.25)
   ├── 3. Evidence Coverage Evaluator    (w=0.20)
   └── 4. Evidence Consistency Evaluator (w=0.20)
               ↓
         Quality Report
     (Aggregated Score vs Task Threshold)
         /               \
   Score >= Threshold     Score < Threshold
       /                   \
   PASS                   FAIL
    ↓                      ↓
Return Response      Attempts < Max Escalations?
                    /                          \
                 YES                            NO
                  ↓                              ↓
            Escalation Policy             Return Explicit
        (Broaden top-k, Graph depth)   INSUFFICIENT EVIDENCE
                  ↓
          Re-Retrieve & Regenerate
```

---

## 1. Verification Signals

All verification signals produce a normalized score in `[0.0, 1.0]` along with human-readable rationales and structured diagnostics.

### A. Citation Grounding Evaluator (`SignalType.CITATION_SUPPORT`)
- **Objective**: Ensure that all cited file paths, symbol names, and line ranges exist in the retrieved evidence chunks.
- **Rules**:
  - Validates citation patterns: `[path/file.py:L10-L25]`, `file.py:10`, `path/file.py`.
  - Compares path against `RetrievedChunk.source_path`.
  - Compares line ranges against `start_line` and `end_line` chunk metadata.
  - Detects ungrounded or hallucinated file citations.
  - Award full score (`1.0`) when response correctly identifies `INSUFFICIENT EVIDENCE` without fabricating citations.
- **Baseline Weight**: `0.35` (Heuristic starting value).

### B. Query Relevance Evaluator (`SignalType.RELEVANCE`)
- **Objective**: Ensure the response directly answers the engineering query and addresses its key symbols and intent.
- **Rules**:
  - Computes keyword recall of non-stopword query tokens in the generated answer.
  - For refusals, verifies that missing information directly refers to query entities.
- **Baseline Weight**: `0.25` (Heuristic starting value).

### C. Evidence Coverage Evaluator (`SignalType.GROUNDEDNESS`)
- **Objective**: Measure the lexical footprint of the retrieved evidence in the answer, as well as chunk utilization.
- **Formula**:
  $$\text{CoverageScore} = 0.70 \times \text{TokenCoverage} + 0.30 \times \text{ChunkUtilization}$$
- **Baseline Weight**: `0.20` (Heuristic starting value).

### D. Evidence Consistency Evaluator (`SignalType.CORRECTNESS`)
- **Objective**: Detect direct factual contradictions or false negative/positive assertions against the evidence.
- **Rules**:
  - Checks for false non-existence claims (e.g. claiming a file or symbol is absent when present in retrieved chunks).
- **Baseline Weight**: `0.20` (Heuristic starting value).

---

## 2. Dynamic Task-Specific Thresholds

Quality thresholds are dynamically resolved per request:
1. `EngTaskRequest.quality_threshold_override` (if explicitly provided).
2. `TaskClassification.quality_threshold` (estimated by M1 Task Intelligence).
3. Fallback: `VerificationConfig.default_quality_threshold` (`0.75`).

| Criticality / Task Type | Example Task | Target Quality Threshold |
|-------------------------|--------------|--------------------------|
| **CRITICAL** | Change Impact / Security Review | `0.85 – 0.90` |
| **HIGH** | Architecture Decision Support | `0.80 – 0.85` |
| **MEDIUM** | Code Explanation / Generation | `0.70 – 0.75` |
| **LOW** | General Repo Assistance | `0.60 – 0.65` |

---

## 3. Bounded Escalation Policy

When candidate output falls below the required threshold, the system executes progressive, deterministic retrieval escalation rather than guessing:

- **Attempt 0**: Initial adaptive retrieval strategy.
- **Attempt 1**: Broaden retrieval scope ($\text{top\_k} \leftarrow \text{top\_k} + 3$, $\text{threshold} \leftarrow \text{threshold} - 0.05$).
- **Attempt 2**: Activate graph augmentation (`mode = graph_augmented`, $\text{hop\_depth} = 2$).
- **Attempt 3**: Maximal capability (`graph_augmented_reranked` with cross-encoder reranking).

### Fallback to Insufficient Evidence
If quality remains below threshold after `max_escalation_attempts` (default: 2), the pipeline terminates and returns an explicit refusal:
> `INSUFFICIENT EVIDENCE: The retrieved repository evidence across N retrieval attempts does not contain sufficient verifiable information...`

This guarantees that the system never fabricates facts under uncertainty.

---

## 4. Telemetry and Provenance

Every verification attempt records:
- `task_id`, `experiment_mode` (`SYSTEM_E`, `SYSTEM_D`, etc.)
- `attempt_number`, `strategy_used`, `chunks_retrieved`
- Individual signal scores, rationales, and diagnostics
- Aggregated quality score and applied threshold
- `passed_quality_gate` boolean
- Accumulated latency, tokens, energy, cost, and carbon emissions
- `git_commit_sha` for experiment reproducibility.
