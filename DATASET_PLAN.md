# DATASET PLAN

Engineering Intelligence Hub — Benchmark Dataset Strategy

---

## Target Benchmark (Master Engineering Intelligence Benchmark — MEIB)

| Parameter | Target |
|---|---|
| Repositories | 4–5 carefully selected open-source projects |
| Development tasks | ~100 (for Phase-1 development and validation) |
| Evaluation tasks (total) | ~400 (Phase-3 complete benchmark) |
| Hidden test set | Assembled after baseline experiments, frozen |
| Temporal separation | Train/validation/test split by commit date where possible |

**Human approval is required before tasks enter the official benchmark.**

---

## Repository Selection Criteria

| Criterion | Rationale |
|---|---|
| Permissive licence (MIT, Apache-2.0, BSD) | Ensures legal use in research |
| Rich commit history (>1 year, >500 commits) | Enables temporal splitting |
| Active issue tracker | Provides incident/bug task material |
| Available tests | Enables test generation/explanation tasks |
| Non-trivial codebase (>10k LOC) | Avoids toy repositories |
| Public/open source | No proprietary data |
| SDLC diversity | Cover different stages and task types |

---

## Phase-1 Pinned Repositories (Finalised)

The following open-source repositories are pinned and registered in `datasets/registry.yaml`:

| Repository | Language | Domain | Pinned Tag | Pinned Commit SHA | Licence | Status |
|---|---|---|---|---|---|---|
| **pallets/flask** | Python | WSGI Web framework | `3.0.3` | `4aa68d5a153fd780b43f769fa5afcaadcf973cb3` | BSD-3-Clause | Pinned & Ingested |
| **fastapi/fastapi** | Python | ASGI API framework | `0.111.0` | `43594b291d9ccf5309320e8b15d0eaef32f30737` | MIT | Pinned & Ingested |

**Candidate Repositories for Phase-2/3 Expansion:**
- `django/django` (Web framework)
- `tiangolo/sqlmodel` (ORM)
- `pandas-dev/pandas` (Data science)

Criteria for final selection:
- Representativeness across SDLC stages
- Quality and quantity of issues/PRs
- Documentation quality (for requirements/architecture tasks)
- Test coverage (for test generation tasks)
- Avoid repositories with primarily non-English documentation

---

## Benchmark Task Types and Distribution (Target)

| SDLC Stage | Task Types | Target Tasks |
|---|---|---|
| Requirements / Architecture | requirement_understanding, architecture_qa | ~60 |
| Development | code_explanation, code_generation, repository_assistance | ~100 |
| Testing / Code Review | test_generation, defect_detection, review_assistance | ~100 |
| Incident / Maintenance | error_analysis, root_cause_assistance, change_understanding | ~80 |
| Mixed / Cross-stage | Various | ~60 |

---

## Benchmark Task Generation Pipeline

1. **Ingest repository** → knowledge store
2. **Generate candidate tasks** → automated extraction from commits, issues, PRs, code
3. **Attach ground truth** → derive from evidence (code, documentation, commit messages)
4. **Attach source evidence** → link to specific file/commit/issue
5. **Validate task quality** → automated checks (non-trivial query, clear ground truth, evidence present)
6. **Human review** → researcher reviews and approves/rejects
7. **Status → APPROVED** → task enters official benchmark

Tasks must remain in `CANDIDATE` status until human approval. Do not run official
experiments against unapproved tasks.

---

## Temporal Splitting Strategy

Where commit history allows:
- **Training set** → tasks derived from repository content before cutoff date
- **Validation set** → tasks derived from content 3–6 months before cutoff
- **Test set** → tasks derived from content after cutoff (frozen, hidden until final evaluation)

This prevents information leakage from future commits into training tasks.

---

## Benchmark Task Schema (Reference)

See `knowledge/schemas/benchmark.py` for the full `BenchmarkTask` Pydantic schema.

Key fields:
- `task_id`, `repository`, `sdlc_stage`, `task_type`
- `difficulty`, `complexity`, `criticality`, `security_sensitivity`
- `query`, `ground_truth`, `acceptable_alternatives`
- `expected_quality_threshold`
- `source_evidence` (list of `SourceEvidence` — required for APPROVED tasks)
- `status` (CANDIDATE → APPROVED)
- `temporal_split`

---

## Licensing and Attribution

All benchmark tasks are derived from publicly available open-source repositories.
The benchmark will cite the source repository and commit for every task.
Benchmark tasks are derived content — licence compatibility must be verified
per repository before publication.

---

## Order of work

No dates (WORK_PLAN C31). In order:
1. Repository selection finalised
2. Initial 100 CANDIDATE tasks generated
3. Human review of initial 100 tasks
4. Full ~400 task CANDIDATE set
5. Human-approved subset for official experiments
6. Hidden test set frozen
