# Master Engineering Intelligence Benchmark (MEIB) — Phase 1

## Overview

The Master Engineering Intelligence Benchmark (MEIB) Phase-1 dataset contains **60 verified, structured engineering tasks** derived from pinned versions of `pallets/flask` (tag `3.0.3`) and `fastapi/fastapi` (tag `0.111.0`).

---

## 1. SDLC Stage Distribution

The benchmark evenly covers all 6 key software development lifecycle stages (10 tasks each):

| SDLC Stage | Task Count | Primary Task Types | Focus Repositories |
|---|---|---|---|
| **Requirements** | 10 | `requirement_understanding`, `requirement_retrieval`, `architecture_qa` | Flask, FastAPI |
| **Architecture / Code Understanding** | 10 | `code_explanation`, `dependency_understanding` | Flask, FastAPI |
| **Development** | 10 | `code_generation`, `repository_assistance` | Flask, FastAPI |
| **Testing** | 10 | `test_generation`, `test_explanation`, `test_failure_analysis` | Flask, FastAPI |
| **Code Review** | 10 | `defect_detection`, `risk_identification`, `review_assistance` | Flask, FastAPI |
| **Maintenance / Operations** | 10 | `error_analysis`, `root_cause_assistance`, `change_understanding` | Flask, FastAPI |
| **Total** | **60** | | |

---

## 2. Benchmark Task Lifecycle & Validation

Every benchmark task follows a strict validation lifecycle:

```
+---------------+      Automated Quality Gate       +---------------+
|   CANDIDATE   | --------------------------------> |   VALIDATED   |
+---------------+   (Query/GT length, schema valid) +---------------+
                                                           |
                                                           | Human Approval &
                                                           | Source Evidence
                                                           v
                                                    +---------------+
                                                    |   APPROVED    |
                                                    +---------------+
```

- **`CANDIDATE`**: Automatically extracted or drafted tasks.
- **`APPROVED`**: Formally validated tasks with verified `source_evidence` and `human_approved_by` reviewer attribution. Only `APPROVED` tasks are evaluated in official research reporting.

---

## 3. Dataset File Location

- Path: `benchmark/data/meib_phase1_tasks.json`
- Schema: Defined in `knowledge/schemas/benchmark.py` (`BenchmarkTask`, `SourceEvidence`, `QualitySignalRequirements`).
