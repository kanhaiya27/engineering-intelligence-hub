# Benchmark fixes 2026-10-05 — approved by Avaneesh, applied (benchmark v1.1)

Drafted 2026-10-05 by Claude from the repositories at the pinned commits (Flask `c12a5d87`,
FastAPI `1c3e6918`). All four were **approved by Avaneesh on 2026-10-05 and applied** to
`benchmark/data/meib_phase1_tasks.json` (task version 1.1). In addition, 12 tasks whose cited
evidence pointed at wrong lines/files got the locations verified against the pinned source
(answers unchanged; also approved): code-011, code-018, dev-025, ops-051, req-003, req-009,
rev-044, rev-048, test-032, test-033, test-035, test-037. Found by the retrieval-label pass
(`docs/RETRIEVAL_LABELS.md`) and re-checked today.

## 1. `eih-phase1-ops-053` (validation) — wrong version

**Problem.** The question and answer say Flask **3.0** removed `JSONEncoder`, `JSONDecoder`
and `tojson_filter`. The pinned `CHANGES.rst` lists the removal under **Version 2.3.0**
(lines 100–101); they were deprecated in **2.2.0** (lines 232–235, `app.json` provider);
3.0.0 only says "Remove previously deprecated code" (line 41). `tojson_filter` does not
appear in the changelog at all.

**Proposed question.** "Which Flask version removed `json.JSONEncoder` / `JSONDecoder` and
the app's `json_encoder` / `json_decoder` attributes, and what replaced them?"

**Proposed answer.** Deprecated in Flask 2.2.0 and removed in 2.3.0; JSON behaviour is
customised through the `app.json` provider interface (`DefaultJSONProvider`) instead.
Evidence: `CHANGES.rst` L100–101 (2.3.0 removal), L232–235 (2.2.0 deprecation).

## 2. `eih-phase1-ops-052` (validation) — error message does not exist

**Problem.** "`AssertionError: A dependency cycle was detected in Depends(...)`" does not
exist anywhere in FastAPI at this commit (`git grep` for cycle/circular/recursion in
`fastapi/dependencies/` finds nothing). The task cannot be answered from evidence.

**Proposed replacement (same stage `maintenance`, type `error_analysis`, same repository).**
Question: "Diagnose this FastAPI startup error: `AssertionError: Cannot specify `Depends` in
`Annotated` and default value together for 'db'`."
Answer: raised by `analyze_param` in `fastapi/dependencies/utils.py` (assertion at L368–371)
when one parameter declares a dependency twice — inside `Annotated[..., Depends(x)]` **and**
as a default value `= Depends(y)`. Fix: declare it once, either in `Annotated` or as the
default.

## 3. `eih-phase1-code-014` (dev) — wrong name for the cache

**Problem.** The answer calls the cache `values: Dict[...]`. At this commit it is the
`dependency_cache: Optional[Dict[Tuple[Callable[..., Any], Tuple[str]], Any]]` parameter of
`solve_dependencies` (`fastapi/dependencies/utils.py` L524, L532, L547).

**Proposed answer.** `solve_dependencies` keeps a `dependency_cache` dict keyed by each
sub-dependant's `cache_key` (the dependency callable + its security scopes). When
`use_cache` is true and the key is already present, the cached value is reused (L593–594);
otherwise the solved value is stored (L605–606). The cache lives for one request, so the
same dependency used by several parameters runs once per request.

## 4. `eih-phase1-rev-045` (dev) — wrong failure for a non-JSON body

**Problem.** The answer says `request.json` is `None` for a non-JSON body, causing
`TypeError`. Executed on Flask 3.0.3 + Werkzeug 3.1.9 (2026-10-05, scratch environment):

| Request | Result |
|---|---|
| non-JSON body (`x=1`) | **415** Unsupported Media Type |
| no body | **415** |
| JSON without `name` | `KeyError: 'name'` → **500** |
| invalid JSON | **400** Bad Request |

**Proposed answer.** For a non-JSON or missing body, `request.json` raises a 415 error
(Werkzeug ≥ 2.3 behaviour; Flask 3.0 requires Werkzeug ≥ 3.0); invalid JSON gives 400; a
JSON body without `name` raises `KeyError` → 500. Fix: `data = request.get_json(silent=True)
or {}` and validate `data.get("name")`, returning 400 when it is missing.
