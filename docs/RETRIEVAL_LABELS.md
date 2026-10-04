# Retrieval Ground-Truth Labels: MEIB v1.0 (WORK_PLAN B1)

| | |
|---|---|
| **File** | `benchmark/data/retrieval_labels_v1.json` (generated; do not hand-edit) |
| **Builder** | `benchmark/retrieval_labels.py` (label directives + resolver) |
| **Schema** | `knowledge/schemas/benchmark.py`: `RetrievalGroundTruth`, `RequiredEvidence`, `RetrievalLabelSet` |
| **Tests** | `tests/test_benchmark/test_retrieval_labels.py` |
| **Scope** | 36 tasks: dev (24) + val (12). The 24 held-out test tasks are **not** labelled here (§4) |
| **Status** | 35 `draft`, 1 `flagged`, 0 `verified`. Every label needs a human check (§3) |
| **Consumer** | Laptop A, Mode R retrieval metrics (WORK_PLAN A4) |

Labels follow the "R" fields of EIH-SWE schema v2 (`MASTER_DATASET_SPECIFICATION.md`
§5): `relevant_files`, `relevant_symbols`, `required_evidence` (file, line span,
why), `graph_paths`, `expected_citations`. They live in a separate file keyed by
`task_id`, so the frozen task file `meib_phase1_tasks.json` is not rewritten.

## 1. How the labels were made

1. **Pinned to the indexed source.** Each repository was checked out at the exact
   commit stored in the Qdrant chunk payloads (`metadata.commit_sha`). Each
   repository has a single commit:

   | Repository | Commit | Indexed chunks / files |
   |---|---|---|
   | pallets/flask | `c12a5d874c5a014495eb2db8a73f40037bc813ac` | 1,489 / 188 |
   | fastapi/fastapi | `1c3e6918750ccb3f20ea260e9a4238ce2c0e5f63` | 18,899 / 1,902 |

   These counts were MEASURED from Qdrant on laptop-b, 2026-10-05.
2. **Directives, not line numbers.** Each label is written as "symbol `X` in
   file `F`", "doc section `H`", "`.. py:data:: NAME`", "whole file", or (rarely)
   an explicit span checked against an anchor text. The builder resolves them
   with Python's `ast` (decorators included) and a fence-aware Markdown/RST
   heading parser. A missing symbol or heading fails the build.
3. **Not derived from retrieval output.** Labels come from reading the question,
   the ground truth and the source. They never come from what the EIH retrievers
   return, since that would make Mode R circular. The index is consulted only
   afterwards, to record which chunks overlap each span (`chunk_ids`). That
   proves the span is retrievable at all; every one of the 76 spans overlaps at
   least one indexed chunk.
4. **Drift detection.** Each span stores `span_sha256` of its text. A test
   recomputes it from the pinned checkout.
5. **Doc example variants.** FastAPI doc pages include near-identical example
   files (`*_an.py`, `*_py310.py`, …). The primary file is in `relevant_files`;
   the variants are in `alternative_files`, and retrieving one counts the same.

Rebuild or verify (needs `.corpus_cache/` checkouts and Qdrant running):

```powershell
# one-time: fetch the pinned commits (source only, ~2,500 files)
git init .corpus_cache/pallets__flask;  git -C .corpus_cache/pallets__flask fetch --depth 1 https://github.com/pallets/flask.git c12a5d874c5a014495eb2db8a73f40037bc813ac;  git -C .corpus_cache/pallets__flask checkout FETCH_HEAD
git init .corpus_cache/fastapi__fastapi; git -C .corpus_cache/fastapi__fastapi fetch --depth 1 https://github.com/fastapi/fastapi.git 1c3e6918750ccb3f20ea260e9a4238ce2c0e5f63; git -C .corpus_cache/fastapi__fastapi checkout FETCH_HEAD

python -m benchmark.retrieval_labels --check   # labels file reproducible?
python -m benchmark.retrieval_labels           # rebuild after editing SPECS
```

## 2. Problems found in the existing tasks (16 of 36)

While labelling, the existing `source_evidence` and `ground_truth` were checked
against the pinned source. **The task file was not changed.** Each problem is
recorded in that label's `ground_truth_issue` field. Fixing the tasks is a
human decision.

**Ground truth wrong or ungroundable (affects Mode Q correctness scoring):**

| Task | Split | Problem |
|---|---|---|
| ops-052 | **val** | The error `AssertionError: A dependency cycle was detected in Depends(...)` does not exist in FastAPI at this commit (`git grep` for cycle/circular/recurs finds nothing). No evidence can be labelled, so the label is **flagged**. Recommend rewriting or removing the task |
| ops-053 | **val** | The ground truth says Flask 3.0 removed `JSONEncoder`/`JSONDecoder`/`tojson_filter`. The pinned `CHANGES.rst` lists that removal under **2.3.0** (L100–101) and never mentions `tojson_filter` |
| rev-045 | dev | **Needs check.** The ground truth says `request.json` is `None` for a non-JSON body. With Werkzeug ≥ 2.3 (Flask here requires ≥ 3.0) it raises 415. Werkzeug is not in the corpus, so this was not verified |
| code-014 | dev | The ground truth calls the cache `values: Dict[...]`; at this commit it is `dependency_cache` keyed by `Dependant.cache_key` |

**Evidence line ranges point at the wrong code (12 tasks):** code-011, code-018,
dev-025, ops-051, req-003, req-009, rev-044, rev-048, test-032, test-033,
test-035, test-037. Examples: `signals.py L10-45` when the file has 17 lines;
`testclient.py L1-30` when the file has 1 line; `globals.py L30-70` citing a
function `_cv_request_lookup` that does not exist. code-014's evidence range is
also off. The new labels replace these spans for retrieval purposes.

**Implications.**
- ops-052 and ops-053 are **validation** tasks, the 12 that P0-3 calibration
  (WORK_PLAN A3) tunes against. Laptop A should exclude or fix them before
  calibrating.
- The 24 test tasks were presumably authored the same way and may carry
  similar errors. The blind pass (§4) should also check each test task's ground
  truth against the source, before the single final run.

## 3. Human verification (required before Mode R results are reported)

For each label, the reviewer opens each `required_evidence` span at the pinned
commit and checks:

1. The span contains what `why` says, and it is needed to answer the question.
2. Nothing essential is missing. Add a directive to `SPECS` if it is.
3. `alternative_files` really are equivalent.
4. If `ground_truth_issue` is set, decide what happens to the task: keep, fix,
   or drop. Record the decision in `PROGRESS-B.md`.

Then set `label_status` to `verified` with `verified_by="<name>"`. Do this in
`SPECS`/the builder so the file stays reproducible. The schema refuses
`verified` without a reviewer name, and a test refuses `verified` until a human
has done it. Until then, Mode R numbers computed from these labels must be
reported as using **draft** labels.

## 4. Held-out test split (24 tasks): not labelled

CLAUDE.md rule 3 forbids inspecting the test split. Decision (2026-10-05):
dev + val now; the test tasks get labelled later in **one blind pass**, under a
protocol agreed by both laptops and added to CLAUDE.md first:

- Done by B, after every system's configuration is frozen, and before the
  final test run.
- The labeller sees only the task file and the pinned source. They never see
  system outputs, scores or retrieval results.
- Labels and any ground-truth fixes are frozen with a SHA-256 hash recorded in
  the manifest before the single run.
- The schema already enforces this: `split="test"` is rejected by
  `RetrievalGroundTruth` until the protocol exists.

## 5. Not done yet

- `graph_paths` are empty. They are filled after the knowledge graph is
  populated (WORK_PLAN B3).
- `relevant_symbols` lists Python symbols and `py:data` names only. Doc
  sections appear in `required_evidence[].symbol`.
- No retrieval metric has been computed. That is Laptop A's A4.
