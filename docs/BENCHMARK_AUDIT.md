# Benchmark audit: dev + val (Step 2d)

**For Avaneesh to approve.** Nothing in the benchmark has been changed by this audit. Every fix
below is a proposal; the task file changes only after your approval (benchmark rule), and every
approved change is then recorded with your name and date, as with v1.1.

Written 2026-10-06. Every claim was checked against the pinned source in `.corpus_cache/`:
- Flask 3.0.3 @ `c12a5d87`
- FastAPI 0.111.0 @ `1c3e6918`

**Scope:** all 36 dev + val tasks. The 24 test tasks are not read here; they go through the two-reviewer
correctness pass (D12, queue `test-correctness-01..04`).

## Summary

| Group | Tasks | Answer or question wrong | Evidence location wrong or missing lines |
|---|---|---|---|
| Corrected and approved on 2026-10-05 (v1.1, `docs/BENCHMARK_FIXES_2026-10-05.md`) | 16 | 4 (fixed) | 12 (fixed) |
| Audited now | 20 | **7** | 8 wrong ranges + 9 with no line numbers |
| **All dev/val** | 36 | **11 of 36 (31%)** | 29 of 36 needed or need evidence fixes |

**Consequence.** The 24 test tasks come from the same pilot authoring process. A similar defect
rate there is likely, which is why the two-reviewer correctness pass (D12) must finish before the
final run. The test-pass build already found 4 test tasks whose cited evidence cannot be shown
(task ids only; the content was not read):
- code-013 and test-036: cited lines run past the end of the file.
- rev-042 and rev-050: long files cited with no lines.

## Answer or question problems (7)

| # | Task | Problem found in the pinned source | Proposed fix |
|---|---|---|---|
| 1 | `code-015` (dev) | `helpers.url_for` binds nothing itself. It delegates to `current_app.url_for` (helpers.py L220). That uses the context's `url_adapter`, applies `inject_url_defaults` and calls `url_adapter.build(...)` (app.py L1068–1077). Arguments after `endpoint` are keyword-only (helpers.py L176–184): there are no positional values | Answer: "`flask.url_for` delegates to `current_app.url_for`, which takes the request/app context's URL adapter (built from `url_map`), applies URL defaults, and calls `url_adapter.build(endpoint, values, method, url_scheme, force_external)`. Unknown keyword values become query-string arguments; `_anchor` is appended; build errors go to `handle_url_build_error`." |
| 2 | `code-016` (val) | "Subclassed … to allow passing extra headers" is not supported by the code: FastAPI passes `headers` straight to Starlette's `__init__` (exceptions.py L65), so Starlette's class already accepts headers. What FastAPI adds is `detail: Any` (any JSON-serialisable value) plus documentation. The default handler is registered for Starlette's `HTTPException` (applications.py L950), so it handles both. It returns no body for statuses that allow none (exception_handlers.py L13–14) | Answer: "FastAPI's `HTTPException` subclasses Starlette's, accepting any JSON-serialisable `detail` and optional `headers`, passed to Starlette's constructor. FastAPI registers `http_exception_handler` for Starlette's `HTTPException` class, so both kinds are turned into a JSON `{"detail": ...}` response with the status code and headers (no body when the status forbids one)." |
| 3 | `dev-023` (dev) | The question asks for a command named `init_db`; the answer registers `'init'`. `AppGroup.command` already wraps the callback in `with_appcontext` (cli.py L406–410), so the explicit decorator is redundant (harmless) | Use `@db_cli.command('init_db')` (or reword the question to `init`). Add: "AppGroup.command applies with_appcontext automatically; the explicit decorator is optional." |
| 4 | `dev-026` (val) | The question asks for `regex`. At the pinned FastAPI, `regex` is deprecated: "Deprecated in FastAPI 0.100.0 and Pydantic v2, use `pattern` instead." (params.py L45–50). The answer silently uses `pattern` | Add: "`regex` is deprecated since 0.100.0; use `pattern`". Add evidence params.py L44–50 (the label lacks it) |
| 5 | `ops-054` (dev) | The question asks how the dependency **requirements** changed; the answer does not state them. pyproject.toml L45: `pydantic>=1.7.4,!=1.8,!=1.8.1,!=2.0.0,!=2.0.1,!=2.1.0,<3.0.0`. Release notes 0.100.0: "compatibility with Pydantic v1 and v2" (release-notes.md L1021–1040) | Add the requirement range and the release-note statement; keep the `_compat` point (`_compat.py` L28–29) |
| 6 | `ops-059` (dev) | Premise: Flask did not "replace" Werkzeug's `Request`; it subclasses it (wrappers.py L18, L26–28). `get_json` is Werkzeug's, not added by Flask. Flask adds `url_rule`, `view_args`, `routing_exception`, `max_content_length` (from `MAX_CONTENT_LENGTH`), `endpoint`, `blueprint(s)`, debug-aware `_load_form_data`, and `on_json_loading_failed` (raises `BadRequest`); it sets `json_module` to `flask.json` (wrappers.py L31–136) | Question: "How does `flask.wrappers.Request` extend Werkzeug's `Request`?" Answer as listed; drop the `get_json` claim |
| 7 | `test-038` (dev) | The pinned docs test async apps with `AsyncClient(app=app, base_url=...)` and `@pytest.mark.anyio` (docs_src/async_tests/test_main.py L1–12). The answer's `httpx.ASGITransport` and `@pytest.mark.asyncio` (needs the pytest-asyncio plugin) appear nowhere in the pinned corpus, so no system can ground that answer in retrieved evidence | Either (a) reword the question to the pinned approach and keep `ASGITransport` as an acceptable alternative, or (b) keep it and mark the task "needs knowledge beyond the corpus". **Recommended: (a)** |

**Correct as written (13):**
- code-017
- rev-043
- rev-046
- rev-047
- dev-021
- dev-028
- dev-030
- ops-058 (see note 2)
- req-002 (see note 1)
- req-005
- req-008
- req-010
- test-034

**Notes for reviewers:**
1. **req-002** asks "What are FastAPI's requirements for automatic OpenAPI documentation?". That is
   vague (`question_clear`), and the answer's "Pydantic models are required" overstates it: type
   hints alone suffice.
2. **ops-058** quotes the error without the quotation marks the real message has:
   `Form data requires "python-multipart" to be installed.` (dependencies/utils.py L67–71).

## Evidence location problems (17)

**Wrong or partial line ranges (8).** The correct spans are those in the retrieval labels
(`benchmark/data/retrieval_labels_v1.json`), plus any additions noted.

| Task | Cited | Pinned location of the evidence |
|---|---|---|
| code-015 | helpers.py L180–260 | helpers.py L176–227; app.py L966–1090 |
| code-016 | exceptions.py L1–35 (docstring only) | exceptions.py L9–65; exception_handlers.py L11–17; applications.py L950 |
| code-017 | helpers.py L300–370 | helpers.py L299–330, L333–372 (minor) |
| rev-043 | templating.py L120–160 | templating.py L153–162 |
| rev-047 | sessions.py L30–70 (session classes, not signing) | sessions.py L307–318; docs/config.rst L114–126 |
| dev-023 | cli.py L400–460 | cli.py L366–388 (`with_appcontext`), L391–413 (`AppGroup`) |
| req-005 | config.py L20–50 (the `Config` class, not DEBUG) | docs/config.rst L45–78; sansio/app.py L549–567; helpers.py L27–32 |
| req-010 | security/oauth2.py L40–90 (partial) | oauth2.py L16–149 (`OAuth2PasswordRequestForm`), L391–485 (`OAuth2PasswordBearer`) |

**File cited with no line numbers (9, ASK_ME L3):**
- dev-021
- dev-028
- dev-030
- ops-058
- req-002
- req-008
- rev-046
- test-034
- test-038

Proposed fix: write the label's spans into the task file.

**Label additions found by this audit** (labels are also drafts awaiting your review, L1):
- rev-046: add async.md L404 (`def` endpoints run in a threadpool; the fix the answer gives).
- dev-026: add params.py L44–50.

## What happens after approval

For each approved item:
1. The task file is updated: question, answer, alternatives, `source_evidence` with exact lines.
   `version` becomes 1.2, with `human_approved_by` = you and the date.
2. The retrieval labels are rebuilt and the benchmark version goes to v1.2.
3. Mode R (provisional) is rerun.

The split assignment does not change, and nothing on the test split is touched.
