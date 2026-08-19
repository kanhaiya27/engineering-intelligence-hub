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

### RD-004 — Sustainability estimation approach (2026-08-19)

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
