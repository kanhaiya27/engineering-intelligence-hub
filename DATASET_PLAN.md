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

## Candidate Repositories (to be finalised)

The following are candidate repositories under consideration. **None are confirmed yet.**

| Repository | Language | Domain | Approximate LOC | Licence |
|---|---|---|---|---|
| pallets/flask | Python | Web framework | ~20k | BSD-3-Clause |
| django/django | Python | Web framework | ~200k | BSD-3-Clause |
| fastapi/fastapi | Python | API framework | ~15k | MIT |
| ansible/ansible | Python | DevOps | ~300k | GPL-3.0 |
| pandas-dev/pandas | Python | Data science | ~200k | BSD-3-Clause |

**Selection will be finalised in Phase-1 (September 2026).**

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

## Timeline

| Milestone | Date |
|---|---|
| Repository selection finalised | September 2026 |
| Initial 100 CANDIDATE tasks generated | September 2026 |
| Human review of initial 100 tasks | October 2026 |
| Full ~400 task CANDIDATE set | October 2026 |
| Human-approved subset (~200 tasks) for official experiments | October 2026 |
| Hidden test set frozen | November 2026 |
