# Phase-2 Task Intelligence Subsystem

## Overview

The Task Intelligence subsystem is the entry point for the **Engineering Intelligence Layer**. It analyzes an incoming `EngTaskRequest` and produces a structured `TaskClassification` that drives downstream retrieval strategy selection, context depth, and quality gate thresholds.

```
                  USER TASK (EngTaskRequest)
                             ↓
              RULE-BASED TASK CLASSIFIER
                             ↓
       ┌─────────────────────┼─────────────────────┐
       ↓                     ↓                     ↓
   SDLC Stage            Task Type             Complexity
 (Requirements,        (e.g., Defect         (Low, Medium,
  Architecture,         Detection,            High, Very High)
  Testing, etc.)        Code Gen, etc.)            │
       │                     │                     │
       └─────────────────────┼─────────────────────┘
                             ↓
             CRITICALITY & SECURITY SENSITIVITY
             (Low, Medium, High, Critical Risk)
                             ↓
              MINIMUM QUALITY THRESHOLD (0.0–1.0)
                             ↓
                     TaskClassification
```

---

## 1. Subsystem Architecture

- **`BaseTaskClassifier`** (`intelligence/base.py`): Abstract interface defining `classify(request: EngTaskRequest) -> TaskClassification`.
- **`RuleBasedTaskClassifier`** (`intelligence/classifier.py`): Pattern-matching classification engine mapping prompt semantics and user hints to `SDLCStage` and `TaskType`.
- **`HeuristicComplexityAnalyzer`** (`intelligence/complexity.py`): Evaluates transparent structural features to estimate `ComplexityLevel`.
- **`HeuristicCriticalityAnalyzer`** (`intelligence/criticality.py`): Assesses operational criticality, `SecuritySensitivity`, and required minimum `quality_threshold`.

---

## 2. Heuristic Complexity Model

> [!NOTE]
> These complexity signals are initial heuristic features designed for rule-based classification and experimental stratification. They are not claimed to be scientifically validated complexity metrics.

The complexity score ($[0.0, 1.0]$) aggregates:
1. **Query Length / Token Span:** Long multi-sentence queries with extensive constraints.
2. **Context Files Count:** Queries referencing multiple explicit repository files.
3. **Architectural & Cross-Module Cues:** Keywords such as `"architecture"`, `"cross-file"`, `"dependency"`, `"dataflow"`, `"lifecycle"`.
4. **Deep Reasoning Cues:** Keywords such as `"root cause"`, `"deadlock"`, `"race condition"`, `"trade-off"`, `"diagnose"`.
5. **Multi-Step Development Cues:** Keywords such as `"refactor"`, `"migrate"`, `"concurrency"`, `"rewrite"`.

Mapped Levels:
- `LOW` ($< 0.30$)
- `MEDIUM` ($0.30 - 0.49$)
- `HIGH` ($0.50 - 0.74$)
- `VERY_HIGH` ($\ge 0.75$)

---

## 3. Criticality & Security Sensitivity

Criticality levels drive the rigor of downstream verification and quality gates:

| Criticality Level | Typical Task Scenarios | Base Quality Threshold |
|---|---|---|
| **LOW** | Informational queries, syntax explanation, documentation lookups | `0.70` |
| **MEDIUM** | Standard code generation, unit test creation, code explanation | `0.75` |
| **HIGH** | Architecture QA, incident analysis, bug/defect diagnosis | `0.85` |
| **CRITICAL** | Security vulnerabilities (CVE, SSTI, SQLi), cryptographic secrets, production outages | `0.90` |

---

## 4. Research Limitations & Honesty

- **Rule-Based:** Classification currently relies on deterministic regex rules and lexical feature maps. No learned machine learning classifier is employed yet.
- **Configurable Quality Thresholds:** Quality thresholds are assigned according to rule-based risk policies and can be overridden by explicit request parameters (`quality_threshold_override`).
