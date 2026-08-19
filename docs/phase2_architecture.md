# Phase-2 Architecture: Engineering Intelligence Layer

## Overview

Phase-2 introduces task-aware adaptation to the Engineering Intelligence Hub. Instead of applying a static RAG pipeline to all engineering questions, the system dynamically analyzes the incoming task to calibrate retrieval strategy, context depth, and verification thresholds.

```
                    USER TASK (EngTaskRequest)
                                ↓
                        TASK ANALYZER (M1)
                                ↓
               ┌────────────────┼────────────────┐
               ↓                ↓                ↓
            SDLC Stage       Task Type       Complexity
               ↓                ↓                ↓
               └────────────────┼────────────────┘
                                ↓
                           CRITICALITY
                                ↓
                      QUALITY REQUIREMENT
                                ↓
                      RETRIEVAL POLICY (M3)
                                ↓
                ┌───────────────┼───────────────┐
                ↓               ↓               ↓
              Dense           BM25           Hybrid
                │               │               │
                └───────────────┼───────────────┘
                                ↓
                      Evidence Set + Graph (M2)
                                ↓
                           Generation
                                ↓
                       Verification (M4)
                                ↓
                        Quality Decision
                                ↓
                     PASS / ESCALATE / FAIL
```

---

## Milestone Execution Order

1. **M1 — Task Intelligence**: Rule-based `TaskClassifier`, heuristic complexity model, criticality & security risk assessment, minimum quality threshold determination. (✅ Complete)
2. **M2 — Engineering Knowledge Graph Foundation**: Concrete graph store implementations (`Neo4jGraphStore`, `InMemoryGraphStore`), AST relation extraction (`ASTGraphExtractor`), provenance tracking, and pipeline builder (`EngineeringGraphBuilder`). (✅ Complete)
3. **M3 — Adaptive Retrieval**: Task-aware retrieval policies mapping `TaskClassification` to tuned search parameters (top-k, weights, graph expansion), supporting Baseline B, System C, and System D. (✅ Complete)
4. **M4 — Quality-Aware Verification**: Deterministic 4-signal quality gate (citation grounding, query relevance, evidence coverage, consistency), dynamic task thresholds, bounded escalation policy, and QualityAwareRAGPipeline. (✅ Complete)
5. **M5 — Controlled Evaluation**: Comparative benchmarking across Baseline A (LLM Only), Baseline B (Fixed RAG), System C (Task-Aware Retrieval), System D (Task-Aware + Graph), and System E (Adaptive + Graph + Quality Verification). (⏳ Next)

