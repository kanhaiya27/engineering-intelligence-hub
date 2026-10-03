# RESEARCH NOTES

Engineering Intelligence Hub — Architecture and Research Decision Log

This document records important research decisions, architectural trade-offs,
and design rationale. Every significant decision should be logged here with
its date, rationale, and alternatives considered.

---

## Decision Log

### RD-001 — Research contribution framing (2026-08-19)

**Decision:** Frame novelty conservatively around the *combination* and *joint evaluation* of:
- Task-aware resource allocation
- Task-specific quality constraints
- Adaptive retrieval + model selection
- SDLC-aware evaluation
- Joint measurement of quality, latency, cost, energy, CO₂e

**Rationale:** RAG, GraphRAG, model routing, green AI, and SE agents are each individually
well-studied. The contribution is the unified framework, the engineering-task-level
resource measurement methodology, and the empirical Pareto analysis across SDLC tasks.

**Alternatives considered:** Claiming individual novelty for each component — rejected
as it would overstate contributions beyond what the literature supports.

---

### RD-002 — Quality as a hard constraint, not an objective (2026-08-19)

**Decision:** The optimisation objective minimises resource consumption *subject to*
quality ≥ task-specific threshold. Quality is never traded away.

**Rationale:** This is the central differentiator from naive energy-saving approaches.
It also matches real engineering practice: a developer needs a correct answer,
not a cheap one.

**Implementation impact:** Quality gate always runs. EscalationExhaustedError is raised
if all escalation attempts fail — the system reports failure rather than returning
a low-quality answer.

---

### RD-003 — Python 3.8 vs 3.11+ (2026-08-19)

**Decision:** Proceed with Python 3.8 for Phase-0 (already installed). Upgrade
to Python 3.11 before Phase-1 (September 2026).

**Rationale:** Python 3.8 is EOL (October 2024). Several Phase-1 libraries
(Qdrant client ≥1.8, newer LangChain) have dropped 3.8 support. Phase-0
schemas and interfaces use `from __future__ import annotations` to remain
compatible.

**Action:** Install Python 3.11 and create a fresh venv before Phase-1 ingestion work.

---

### RD-005 — AST Code Chunker & Line Boundary Provenance (2026-08-19)

**Decision:** Parse Python source code using `ast.parse` to extract semantic boundaries (`FunctionDef`, `AsyncFunctionDef`, `ClassDef`), recording 1-indexed `start_line` and `end_line`.
**Rationale:** Standard arbitrary character/token chunkers slice across function signatures and loop bodies, destroying code syntax. Preserving AST boundaries ensures chunks remain syntactically coherent units of engineering knowledge.

---

### RD-006 — BM25Plus for Software Engineering Retrieval (2026-08-19)

**Decision:** Use `BM25Plus` from `rank_bm25` rather than standard Robertson `BM25Okapi`.
**Rationale:** `BM25Okapi` produces negative IDF values when terms appear in > 50% of documents (common in small repositories or targeted file searches). `BM25Plus` guarantees strictly positive IDF values ($> 0$), ensuring stable ranking across corpus sizes from $N=1$ to $N=100,000$.

---

### RD-007 — Dual-Tier Sustainability Measurement (2026-08-19)

**Decision:** Formally partition sustainability accounting into Tier 1 (Direct NVIDIA NVML Hardware Power Sampling for local GPU models like BGE Small) and Tier 2 (TDP Proxy Modelling for cloud LLM APIs).
**Rationale:** Cloud API providers do not expose real-time power draw. Reporting cloud energy without declaring it as an estimate breaches scientific honesty.

---

### RD-008 — Grounded RAG Citation & Hallucination Guardrails (2026-08-19)

**Decision:** Enforce structured citation requirements and strict `SUPPORTED BY EVIDENCE` vs `INSUFFICIENT EVIDENCE` prompting in `BaselineRAGPipeline`.
**Rationale:** Software engineering RAG systems must explicitly signal uncertainty or missing repository evidence rather than hallucinating APIs, parameter names, or configuration options.

---

### RD-009 — Rule-Based Task Intelligence & Transparent Heuristics (2026-08-20)

**Decision:** Implement Phase-2 Task Intelligence using transparent rule-based lexical matching and heuristic scoring rather than a black-box machine learning classifier.
**Rationale:** Establishing baseline task-aware routing requires interpretable, deterministic classification features. Claiming learned classification without establishing rule-based baselines would violate scientific rigor. Transparent heuristics for complexity and criticality allow controlled ablation studies across SDLC stages.

---

### RD-010 — Provenance-Preserving Knowledge Graph Architecture (2026-08-20)

**Decision:** Maintain strict 1-indexed source code line numbers, commit SHAs, and deterministic identity keys across all knowledge graph nodes and edges.
**Rationale:** Software engineering RAG systems must never hallucinate relationships or disconnected facts. Grounding graph nodes directly into AST syntax trees and verifiable version control commits enables deterministic neighborhood context injection for downstream adaptive retrieval (M3).

---

### RD-009 — Sustainability estimation approach (2026-08-19)

**Decision:** Use proxy-based estimates (TDP × utilisation × latency) for Phase-0/1.
Attempt NVML measurement for local models. Defer RAPL/hardware-level measurement.

**Rationale:** True energy measurement requires controlled hardware (power meters,
RAPL access on Linux, NVML). For API-based models, the energy occurs on provider
hardware — we cannot measure it directly. Proxy estimates allow comparative
experiments while being honest about their limitations.

**System boundary:**
- Included: local CPU/GPU inference energy (proxy), token counts
- Excluded: network, data centre embodied carbon, LLM training energy

**References to add:** Patterson et al. (2021), Lannelongue et al. (2021).

---

### RD-005 — JSONL for experiment logging (2026-08-19)

**Decision:** Use JSONL (JSON Lines) for experiment result storage.

**Rationale:**
- Append-only: safe for concurrent writers
- Streaming-friendly: can analyse before experiment completes
- Directly loadable: pandas `read_json(lines=True)`, DuckDB `read_json_auto()`
- Simple: no database dependency for logging

**Alternative considered:** SQLite — more structured but adds dependency and
locking complexity for concurrent experiments.

---

### RD-006 — Proposed research metrics labelling (2026-08-19)

**Decision:** Three proposed metrics are labelled explicitly as *PROPOSED RESEARCH METRICS*
in code comments and documentation:
1. Energy per Successful Engineering Task (J/task)
2. CO₂e per Successful Engineering Task (gCO₂e/task)
3. Quality-Constrained Energy Efficiency (quality-points per joule)

**Rationale:** These are not established industry standards. Claiming them as
standard metrics would be academically misleading.

---

### RD-007 — Retrieval strategy registry design (2026-08-19)

**Decision:** Named retrieval strategies are loaded from configs/retrieval.yaml.
Task-type → strategy mapping is in retrieval/router.py. Override possible per experiment.

**Rationale:** Fully configurable without code changes. Ablation studies can
reference different strategy names in experiment configs.

**Phase-2 extension:** The router will use task classification features (complexity,
criticality) to further refine strategy selection within the named set.

---

### RD-008 — Rule-based Task Intelligence for Phase-2 M1 (2026-08-20)

**Decision:** Implement rule-based classification and heuristic complexity/criticality estimation for M1.

**Rationale:**
- Fast, zero-inference-cost task routing.
- Fully interpretable: no black-box routing errors.
- Provides a stable, deterministic foundation before introducing learned routing in later phases.

---

### RD-009 — Provenance-Preserving Knowledge Graph Architecture (2026-08-20)

**Decision:** Deterministic URIs (`func:{repo}:{commit}:{path}:{name}:{line}`) and mandatory provenance metadata (`commit_sha`, `start_line`, `end_line`) for all graph entities.

**Rationale:**
- Idempotent ingestion across multiple pipeline runs.
- Prevents unverifiable facts in the graph context.
- Enables precise line-level citation matching during verification.

---

### RD-010 — Heuristic Adaptive Retrieval Policies for Phase-2 M3 (2026-08-20)

**Decision:** All task-type-to-strategy mappings and criticality escalations are explicitly labelled as baseline heuristic configurations.

**Rationale:**
- Establishes a concrete, runnable baseline (System C, System D).
- Prevents premature novelty or optimality claims prior to controlled M5 evaluation.

---

### RD-012: Phase-2 M5 Controlled Evaluation Protocol, Splits, and Quality-Constrained Efficiency
- **Date**: 2026-08-20
- **Context**: Evaluating 5 distinct system configurations (Baseline A, Baseline B, System C, System D, System E) on the 60-task benchmark across quality, efficiency, cost, energy, and carbon.
- **Decision**:
  1. Freeze the 60 Phase-1 tasks as `v1.0-phase1-60`.
  2. Implement deterministic stratified splitting (Seed = 42) into Dev (24 tasks, 40%), Val (12 tasks, 20%), and Held-Out Test (24 tasks, 40%) balanced across 6 SDLC stages and 2 repositories.
  3. Enforce the Quality Constraint: resource savings are only valid if answer quality meets or exceeds the task threshold; otherwise flagged as `INVALID SAVING`.
  4. Categorize all telemetry under strict 3-tier provenance (`MEASURED`, `ESTIMATED`, `DERIVED`).
  5. Structure evaluation into 4 sequential ablation transitions: Delta(A->B), Delta(B->C), Delta(C->D), Delta(D->E) and 2D Pareto frontiers.
  6. Restrict current execution to Dev split verification with mocks, preserving the Held-Out Test set frozen.
- **Impact**: Provides a scientifically rigorous, reproducible, and vendor-neutral evaluation foundation.

---

### RD-011 — Deterministic Quality Verification & Bounded Escalation (2026-08-20)

**Decision:** Implement four deterministic verification signals (Citation Grounding, Query Relevance, Evidence Coverage, Consistency) with configurable baseline weights (0.35, 0.25, 0.20, 0.20) and bounded retrieval escalation.

**Rationale:**
- **Reproducibility**: Deterministic verification ensures consistent experimental measurements without non-deterministic LLM judge hallucination or variance.
- **Provenance Verification**: Validates citations directly against retrieved chunk file paths and line ranges.
- **Bounded Resource Overhead**: Escalation is strictly capped (default max 2 attempts) to prevent latency/energy explosion.
- **Fail-Safe Integrity**: When evidence is inadequate after escalation, the pipeline explicitly returns `INSUFFICIENT EVIDENCE` rather than delivering low-confidence hallucinations.

---

## Open Research Questions

1. How much does retrieval strategy choice affect quality vs. energy trade-offs
   across different SDLC task types?
2. Does model routing (small → large escalation) achieve a better Pareto frontier
   than fixed model selection at the quality threshold boundary?
3. Can graph-augmented retrieval improve groundedness for architecture and
   dependency tasks without excessive latency overhead?
4. What quality thresholds are appropriate per SDLC stage? (Requires empirical calibration.)
5. How stable are energy proxy estimates compared to direct hardware measurement?

---

## Literature to Review

- Patterson et al. (2021). "Carbon and the Carbon Footprint of Machine Learning."
- Lannelongue et al. (2021). "Green Algorithms."
- Lewis et al. (2020). "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks."
- Edge et al. (2024). "From Local to Global: A Graph RAG Approach."
- Anthropic / OpenAI efficiency papers (TBD).
- SE-specific RAG papers (TBD — search IEEE, ACM DL).
