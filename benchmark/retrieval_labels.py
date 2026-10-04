"""
Retrieval ground-truth labels for the MEIB v1.0 dev + val tasks (WORK_PLAN B1).

Labels are written as directives ("symbol X in file Y", "doc section Z") and
resolved against the repositories checked out at the exact commits that were
ingested into Qdrant. Line numbers are never typed by hand: if a symbol or
heading does not exist at the pinned commit the build fails.

Protocol (docs/RETRIEVAL_LABELS.md):
- Only dev + val tasks are labelled here. The 24 held-out test tasks are never
  loaded by this module (CLAUDE.md rule 3); they get a separate blind pass.
- Labels come from reading the source and the task's question/ground truth, never
  from what the retrieval system returns (that would make Mode R circular).
- Every label starts as ``draft``; a named human reviewer promotes it to ``verified``.

    python -m benchmark.retrieval_labels            # rebuild the labels file
    python -m benchmark.retrieval_labels --check    # verify it is up to date
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

from knowledge.schemas.benchmark import (
    RequiredEvidence,
    RetrievalGroundTruth,
    RetrievalLabelSet,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "benchmark" / "data"
TASKS_PATH = DATA_DIR / "meib_phase1_tasks.json"
SPLITS_PATH = DATA_DIR / "splits_v1.0.json"
LABELS_PATH = DATA_DIR / "retrieval_labels_v1.json"
CORPUS_CACHE = REPO_ROOT / ".corpus_cache"
REGISTRY_PATH = REPO_ROOT / "datasets" / "registry.yaml"

LABELS_VERSION = "1.0-draft"
ANNOTATOR = "laptop-b (Claude Opus 5.5 draft; requires human verification)"
CREATED_AT = "2026-10-05T00:00:00+00:00"

# Commits ingested into the Qdrant collection eih_knowledge (read from chunk
# payload metadata.commit_sha on 2026-10-05; one commit per repository).
PINNED_COMMITS: Dict[str, str] = {
    "pallets/flask": "c12a5d874c5a014495eb2db8a73f40037bc813ac",
    "fastapi/fastapi": "1c3e6918750ccb3f20ea260e9a4238ce2c0e5f63",
}

QDRANT_URL = "http://localhost:6333"
COLLECTION = "eih_knowledge"


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sym:
    """A Python symbol by qualified name (all same-named defs are merged)."""
    file: str
    qualname: str
    why: str


@dataclass(frozen=True)
class Section:
    """A Markdown/RST section from its heading to the next heading of equal or higher rank."""
    file: str
    heading: str
    why: str


@dataclass(frozen=True)
class PyData:
    """An RST ``.. py:data:: NAME`` block up to the next directive or heading."""
    file: str
    name: str
    why: str


@dataclass(frozen=True)
class WholeFile:
    file: str
    why: str


@dataclass(frozen=True)
class Lines:
    """Explicit span, anchored by text that must appear on its first line."""
    file: str
    start: int
    end: int
    anchor: str
    why: str


Directive = Sym | Section | PyData | WholeFile | Lines


@dataclass(frozen=True)
class LabelSpec:
    evidence: Tuple[Directive, ...] = ()
    alternatives: Tuple[str, ...] = ()
    flagged: bool = False
    ground_truth_issue: Optional[str] = None
    notes: Optional[str] = None
    extra_symbols: Tuple[str, ...] = field(default=())


_ERR = "fastapi/dependencies/utils.py"

SPECS: Dict[str, LabelSpec] = {
    # ----------------------------- dev -----------------------------------
    "eih-phase1-code-014": LabelSpec(
        evidence=(
            Sym(_ERR, "solve_dependencies", "Looks up and stores solved sub-dependencies in dependency_cache when use_cache is set."),
            Lines("fastapi/dependencies/models.py", 58, 58, "self.cache_key", "Defines cache_key = (call, sorted security scopes), the cache key."),
        ),
        ground_truth_issue="Ground truth names the cache 'values: Dict[...]'; at the pinned commit it is "
        "'dependency_cache' keyed by Dependant.cache_key. Evidence lines 450-520 cover analyze_param..solve_generator, "
        "not solve_dependencies (524-649).",
    ),
    "eih-phase1-code-015": LabelSpec(
        evidence=(
            Sym("src/flask/helpers.py", "url_for", "Public url_for; delegates to current_app.url_for."),
            Sym("src/flask/app.py", "Flask.url_for", "Builds the URL with the bound URL adapter; extra values become query args."),
        ),
    ),
    "eih-phase1-code-017": LabelSpec(
        evidence=(
            Sym("src/flask/helpers.py", "flash", "Appends (category, message) to session['_flashes']."),
            Sym("src/flask/helpers.py", "get_flashed_messages", "Pops _flashes from the session, with category filtering."),
        ),
    ),
    "eih-phase1-code-018": LabelSpec(
        evidence=(Sym("fastapi/routing.py", "APIRouter.include_router", "Copies child routes with merged prefix, tags and dependencies."),),
        ground_truth_issue="Evidence lines 500-600 are APIRoute/APIRouter.__init__; include_router is 1072-1310.",
    ),
    "eih-phase1-dev-023": LabelSpec(
        evidence=(
            Sym("src/flask/cli.py", "AppGroup", "Click group whose commands are wrapped in with_appcontext."),
            Sym("src/flask/cli.py", "with_appcontext", "Decorator that pushes an app context for a command."),
        ),
    ),
    "eih-phase1-dev-025": LabelSpec(
        evidence=(
            Sym("src/flask/sansio/scaffold.py", "Scaffold.errorhandler", "Decorator registering a handler for a status code or exception."),
            Sym("src/flask/sansio/scaffold.py", "Scaffold.register_error_handler", "Non-decorator form of errorhandler."),
        ),
        ground_truth_issue="Evidence cites src/flask/app.py L1000-1080 (inside Flask.url_for); errorhandler lives in sansio/scaffold.py.",
    ),
    "eih-phase1-dev-028": LabelSpec(
        evidence=(
            Section("docs/en/docs/tutorial/middleware.md", "Create a middleware", "@app.middleware('http'), call_next, and the X-Process-Time example (subsection included)."),
            WholeFile("docs_src/middleware/tutorial001.py", "The add_process_time_header example code included by the doc."),
        ),
    ),
    "eih-phase1-dev-030": LabelSpec(
        evidence=(
            Section("docs/en/docs/advanced/events.md", "Lifespan", "The @asynccontextmanager lifespan pattern and FastAPI(lifespan=...)."),
            WholeFile("docs_src/events/tutorial003.py", "The lifespan example code included by the doc."),
        ),
    ),
    "eih-phase1-ops-051": LabelSpec(
        evidence=(
            Lines("src/flask/globals.py", 35, 51, '_no_req_msg = """', "The 'Working outside of request context' message and the request/session proxies that raise it."),
            Sym("src/flask/app.py", "Flask.test_request_context", "The fix named in the ground truth for tests."),
        ),
        ground_truth_issue="Evidence cites globals.py L30-70 and a function _cv_request_lookup; the file has 51 lines and "
        "no such function (the error comes from LocalProxy unbound_message).",
    ),
    "eih-phase1-ops-054": LabelSpec(
        evidence=(
            Lines("fastapi/_compat.py", 28, 29, "PYDANTIC_VERSION", "PYDANTIC_V2 flag selecting the v1/v2 compatibility branch."),
        ),
        notes="Only the version flag is labelled; the v2 and v1 branches (L48 / L282) are large. Release-notes "
        "coverage of 0.100.0 not checked; add if found during verification.",
    ),
    "eih-phase1-ops-058": LabelSpec(
        evidence=(
            Sym(_ERR, "multipart_not_installed_error", "The exact error text."),
            Sym(_ERR, "check_file_field", "Raises RuntimeError(multipart_not_installed_error) when the import fails."),
            Lines("docs/en/docs/tutorial/request-forms.md", 5, 8, "", "Docs: install python-multipart to use forms."),
        ),
    ),
    "eih-phase1-ops-059": LabelSpec(
        evidence=(Sym("src/flask/wrappers.py", "Request", "Flask's Request subclass of Werkzeug's Request."),),
    ),
    "eih-phase1-req-005": LabelSpec(
        evidence=(
            PyData("docs/config.rst", "DEBUG", "Documents the DEBUG config key and FLASK_DEBUG."),
            Section("docs/config.rst", "Debug Mode", "Debug mode via the CLI --debug option / FLASK_DEBUG."),
            Sym("src/flask/sansio/app.py", "App.debug", "app.debug property reads/writes config['DEBUG']."),
            Sym("src/flask/helpers.py", "get_debug_flag", "Reads FLASK_DEBUG from the environment."),
        ),
    ),
    "eih-phase1-req-008": LabelSpec(
        evidence=(
            Section("docs/en/docs/tutorial/background-tasks.md", "Using `BackgroundTasks`", "Declare a BackgroundTasks parameter."),
            Section("docs/en/docs/tutorial/background-tasks.md", "Add the background task", "background_tasks.add_task(...)."),
            WholeFile("docs_src/background_tasks/tutorial001.py", "The example code included by the doc."),
        ),
    ),
    "eih-phase1-req-009": LabelSpec(
        evidence=(
            WholeFile("src/flask/signals.py", "Blinker Namespace and every core signal."),
            Section("docs/signals.rst", "Core Signals", "Docs for the core signals."),
        ),
        ground_truth_issue="Evidence cites signals.py L10-45; the file has 17 lines.",
    ),
    "eih-phase1-req-010": LabelSpec(
        evidence=(
            Sym("fastapi/security/oauth2.py", "OAuth2PasswordBearer", "Extracts the bearer token from the Authorization header."),
            Sym("fastapi/security/oauth2.py", "OAuth2PasswordRequestForm", "Parses username/password/scope/grant_type form fields."),
        ),
    ),
    "eih-phase1-rev-043": LabelSpec(
        evidence=(Sym("src/flask/templating.py", "render_template_string", "Renders a template from a source string (the SSTI sink)."),),
    ),
    "eih-phase1-rev-044": LabelSpec(
        evidence=(
            Section("docs/en/docs/tutorial/path-params.md", "Path parameters with types", "Type annotations on path parameters."),
            Section("docs/en/docs/tutorial/path-params.md", "Data validation", "Validation errors when the annotation does not match."),
            Sym(_ERR, "get_typed_signature", "Reads the endpoint signature's annotations."),
            Sym(_ERR, "analyze_param", "Turns each annotated parameter into a validated field."),
        ),
        ground_truth_issue="Evidence cites fastapi/routing.py L180-220 (serialize_response..get_request_handler); "
        "parameter analysis is in fastapi/dependencies/utils.py.",
    ),
    "eih-phase1-rev-045": LabelSpec(
        evidence=(Sym("src/flask/wrappers.py", "Request.on_json_loading_failed", "Turns JSON decode failures into BadRequest."),),
        ground_truth_issue="NEEDS CHECK: ground truth says request.json is None for a non-JSON body. With "
        "Werkzeug >= 2.3 (Flask at this commit requires >= 3.0) it raises 415 Unsupported Media Type instead. "
        "Werkzeug is not in the corpus, so this was not verified here.",
    ),
    "eih-phase1-rev-048": LabelSpec(
        evidence=(
            Section("docs/en/docs/tutorial/path-params-numeric-validations.md", "Number validations: greater than or equal", "ge/le constraints."),
            Sym("fastapi/param_functions.py", "Query", "Query(...) accepts ge, gt, le, lt."),
        ),
        ground_truth_issue="Evidence cites fastapi/params.py L20-50 (Param.__init__ start), not the Query ge/le docs.",
    ),
    "eih-phase1-test-034": LabelSpec(
        evidence=(
            Section("docs/en/docs/advanced/testing-dependencies.md", "Use the `app.dependency_overrides` attribute", "How to override and reset."),
            WholeFile("docs_src/dependency_testing/tutorial001.py", "Example override test code."),
        ),
        alternatives=(
            "docs_src/dependency_testing/tutorial001_an.py",
            "docs_src/dependency_testing/tutorial001_an_py310.py",
            "docs_src/dependency_testing/tutorial001_an_py39.py",
            "docs_src/dependency_testing/tutorial001_py310.py",
        ),
    ),
    "eih-phase1-test-035": LabelSpec(
        evidence=(
            Lines("src/flask/globals.py", 17, 33, '_no_app_msg = """', "'Working outside of application context' message and the current_app/g proxies."),
            Sym("src/flask/ctx.py", "AppContext.push", "Pushing an app context binds _cv_app."),
        ),
        ground_truth_issue="Evidence cites globals.py L20-60; the file has 51 lines.",
    ),
    "eih-phase1-test-037": LabelSpec(
        evidence=(
            Section("docs/testing.rst", "Accessing and Modifying the Session", "Session access with the test client."),
            Sym("src/flask/testing.py", "FlaskClient.session_transaction", "Opens/saves the session around a block."),
        ),
        ground_truth_issue="Evidence cites testing.py L50-100 (EnvironBuilder), not FlaskClient.",
    ),
    "eih-phase1-test-038": LabelSpec(
        evidence=(
            Section("docs/en/docs/advanced/async-tests.md", "Example", "AsyncClient + ASGITransport example."),
            WholeFile("docs_src/async_tests/test_main.py", "The async test included by the doc."),
            WholeFile("docs_src/async_tests/main.py", "The app under test."),
        ),
    ),
    # ----------------------------- val -----------------------------------
    "eih-phase1-code-011": LabelSpec(
        evidence=(
            Sym("src/flask/ctx.py", "RequestContext.push", "Pushes app context if needed, sets _cv_request, opens session."),
            Sym("src/flask/ctx.py", "RequestContext.pop", "Runs teardown_request functions and resets the context var."),
        ),
        ground_truth_issue="Evidence cites ctx.py L200-280 (has_request_context..AppContext); RequestContext.push/pop are 367-431.",
    ),
    "eih-phase1-code-016": LabelSpec(
        evidence=(
            Sym("fastapi/exceptions.py", "HTTPException", "Subclass of Starlette HTTPException with headers and any detail."),
            Sym("fastapi/exception_handlers.py", "http_exception_handler", "Default handler returning a JSONResponse."),
            Section("docs/en/docs/tutorial/handling-errors.md", "Use `HTTPException`", "Docs for raising HTTPException."),
        ),
    ),
    "eih-phase1-dev-021": LabelSpec(
        evidence=(Section("docs/tutorial/factory.rst", "The Application Factory", "create_app(test_config=None) factory."),),
    ),
    "eih-phase1-dev-026": LabelSpec(
        evidence=(
            Section("docs/en/docs/tutorial/query-params-str-validations.md", "Add more validations", "min_length / max_length."),
            Section("docs/en/docs/tutorial/query-params-str-validations.md", "Add regular expressions", "pattern= (and the old regex=)."),
            WholeFile("docs_src/query_params_str_validations/tutorial004.py", "Example with min_length, max_length and pattern."),
            Sym("fastapi/param_functions.py", "Query", "Query(...) signature with the validation arguments."),
        ),
        alternatives=(
            "docs_src/query_params_str_validations/tutorial004_an.py",
            "docs_src/query_params_str_validations/tutorial004_an_py310.py",
            "docs_src/query_params_str_validations/tutorial004_an_py39.py",
            "docs_src/query_params_str_validations/tutorial004_py310.py",
        ),
    ),
    "eih-phase1-ops-052": LabelSpec(
        flagged=True,
        ground_truth_issue="The error 'AssertionError: A dependency cycle was detected in Depends(...)' does not "
        "exist in FastAPI at the pinned commit: git grep for cycle/circular/recurs in fastapi/dependencies and "
        "fastapi/routing.py finds nothing. The task premise cannot be grounded in the corpus.",
        notes="No evidence span can be labelled. Recommend rewriting or removing this task (human decision).",
    ),
    "eih-phase1-ops-053": LabelSpec(
        evidence=(
            Section("CHANGES.rst", "Version 2.3.0", "Removal of json_encoder/json_decoder and json.JSONEncoder/JSONDecoder."),
            Section("CHANGES.rst", "Version 3.0.0", "3.0.0 'Remove previously deprecated code'."),
        ),
        ground_truth_issue="Ground truth says Flask 3.0 removed JSONEncoder/JSONDecoder/tojson_filter. The pinned "
        "CHANGES.rst lists the JSONEncoder/JSONDecoder removal under 2.3.0 (L100-101) and never mentions "
        "tojson_filter. Ground truth contradicts the corpus.",
    ),
    "eih-phase1-req-002": LabelSpec(
        evidence=(
            Section("docs/en/docs/features.md", "Based on open standards", "OpenAPI + JSON Schema."),
            Section("docs/en/docs/features.md", "Automatic docs", "Swagger UI at /docs and ReDoc at /redoc."),
        ),
    ),
    "eih-phase1-req-003": LabelSpec(
        evidence=(
            Section("docs/blueprints.rst", "Registering Blueprints", "register_blueprint(bp, url_prefix=...)."),
            Sym("src/flask/sansio/blueprints.py", "BlueprintSetupState.__init__", "Resolves url_prefix from options or the blueprint default."),
            Sym("src/flask/sansio/blueprints.py", "Blueprint.register", "Registers deferred functions and nested blueprints on the app."),
            Sym("src/flask/sansio/app.py", "App.register_blueprint", "Entry point called by the app."),
        ),
        ground_truth_issue="Evidence cites src/flask/blueprints.py L50-120; Blueprint.register is in sansio/blueprints.py.",
    ),
    "eih-phase1-rev-046": LabelSpec(
        evidence=(Section("docs/en/docs/async.md", "In a hurry?", "Use def, not async def, for blocking libraries."),),
    ),
    "eih-phase1-rev-047": LabelSpec(
        evidence=(
            PyData("docs/config.rst", "SECRET_KEY", "Secret key used to sign the session cookie."),
            Sym("src/flask/sessions.py", "SecureCookieSessionInterface.get_signing_serializer", "Builds the itsdangerous serializer from secret_key."),
        ),
    ),
    "eih-phase1-test-032": LabelSpec(
        evidence=(
            WholeFile("fastapi/testclient.py", "Re-exports Starlette's TestClient."),
            Section("docs/en/docs/tutorial/testing.md", "Using `TestClient`", "TestClient usage."),
        ),
        ground_truth_issue="Evidence cites testclient.py L1-30; the file has 1 line.",
    ),
    "eih-phase1-test-033": LabelSpec(
        evidence=(
            Sym("src/flask/testing.py", "FlaskCliRunner", "CliRunner subclass invoking commands with the app's ScriptInfo."),
            Sym("src/flask/app.py", "Flask.test_cli_runner", "Creates the runner."),
            Section("docs/testing.rst", "Running Commands with the CLI Runner", "Docs for test_cli_runner."),
        ),
        ground_truth_issue="Evidence cites testing.py L120-170 (FlaskClient); FlaskCliRunner is 265-298.",
    ),
}


# ---------------------------------------------------------------------------
# Resolution against the pinned source
# ---------------------------------------------------------------------------


class LabelError(RuntimeError):
    pass


def _registry_repo_id(repository: str) -> Optional[str]:
    """The ``repo_id`` that scripts/ingest_corpus.py uses for ``owner/name``."""
    owner, _, name = repository.partition("/")
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        entries = yaml.safe_load(f).get("repositories", [])
    for e in entries:
        if e.get("owner") == owner and e.get("name") == name:
            return e["repo_id"]
    return None


def repo_dir(repository: str) -> Path:
    """Checkout of ``owner/name`` under .corpus_cache/.

    Accepts the ingest_corpus layout (``.corpus_cache/<repo_id>``, e.g. ``flask``)
    and the older ``owner__name`` layout; returns the first that exists, else the
    ingest_corpus path.
    """
    repo_id = _registry_repo_id(repository)
    candidates = [CORPUS_CACHE / repo_id] if repo_id else []
    candidates.append(CORPUS_CACHE / repository.replace("/", "__"))
    for path in candidates:
        if (path / ".git").exists():
            return path
    return candidates[0]


def checkout_sha(repository: str) -> Optional[str]:
    """Commit checked out in ``repo_dir(repository)``, or None if unavailable."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir(repository)), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def _read(repository: str, rel: str) -> List[str]:
    path = repo_dir(repository) / rel
    if not path.is_file():
        raise LabelError(f"{repository}: {rel} not found at the pinned commit")
    return path.read_text(encoding="utf-8").splitlines()


def _python_symbols(source: str) -> List[Tuple[str, int, int]]:
    tree = ast.parse(source)
    out: List[Tuple[str, int, int]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([d.lineno for d in n.decorator_list] + [n.lineno])
                out.append((prefix + n.name, start, n.end_lineno or n.lineno))
                walk(n, prefix + n.name + ".")
            elif node is tree and isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        out.append((t.id, n.lineno, n.end_lineno or n.lineno))

    walk(tree, "")
    return out


def _md_headings(lines: Sequence[str]) -> List[Tuple[int, str, int]]:
    """(rank, text, line) for Markdown headings outside fenced code."""
    out, fence = [], False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        m = None if fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


def _rst_headings(lines: Sequence[str]) -> List[Tuple[int, str, int]]:
    """(rank, text, first line) for RST titles.

    rank = order in which each adornment style first appears; first line is the
    overline if there is one, otherwise the title text line (1-based).
    """
    adornment = r"^([=\-~^\"'`#*+])\1{2,}\s*$"
    out, ranks = [], {}
    for i in range(1, len(lines)):  # i = 0-based index of the underline
        under, title = lines[i], lines[i - 1]
        if (
            re.match(adornment, under)
            and title.strip()
            and not re.match(adornment, title)
            and len(under.rstrip()) >= len(title.rstrip())
            and not title.startswith((" ", "\t", ".."))
        ):
            overlined = i >= 2 and lines[i - 2].strip() == under.strip()
            key = (under[0], overlined)
            ranks.setdefault(key, len(ranks))
            first_line = (i - 1) if overlined else i  # 1-based
            out.append((ranks[key], title.strip(), first_line))
    return out


def _section(lines: Sequence[str], rel: str, heading: str) -> Tuple[int, int]:
    heads = _md_headings(lines) if rel.endswith(".md") else _rst_headings(lines)
    matches = [h for h in heads if h[1] == heading]
    if len(matches) != 1:
        raise LabelError(f"{rel}: heading {heading!r} found {len(matches)} times (need exactly 1)")
    rank, _, start = matches[0]
    end = len(lines)
    for r, _, ln in heads:
        if ln > start and r <= rank:
            end = ln - 1
            break
    # Drop trailing blank lines and RST link targets (".. _name:") that belong
    # to the next section.
    while end > start and (not lines[end - 1].strip() or re.match(r"^\.\. _[^:]+:\s*$", lines[end - 1])):
        end -= 1
    return start, end


def _pydata(lines: Sequence[str], rel: str, name: str) -> Tuple[int, int]:
    starts = [i for i, l in enumerate(lines, 1) if l.strip() == f".. py:data:: {name}"]
    if len(starts) != 1:
        raise LabelError(f"{rel}: py:data {name} found {len(starts)} times")
    start = starts[0]
    end = len(lines)
    for i in range(start + 1, len(lines) + 1):
        l = lines[i - 1]
        if l.startswith(".. ") or (i < len(lines) and re.match(r"^([=\-~^])\1{2,}\s*$", lines[i])):
            end = i - 1
            break
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def resolve(repository: str, d: Directive) -> Tuple[int, int, Optional[str]]:
    lines = _read(repository, d.file)
    if isinstance(d, Sym):
        hits = [s for s in _python_symbols("\n".join(lines)) if s[0] == d.qualname]
        if not hits:
            raise LabelError(f"{d.file}: symbol {d.qualname!r} not found")
        return min(h[1] for h in hits), max(h[2] for h in hits), d.qualname
    if isinstance(d, Section):
        a, b = _section(lines, d.file, d.heading)
        return a, b, d.heading
    if isinstance(d, PyData):
        a, b = _pydata(lines, d.file, d.name)
        return a, b, d.name
    if isinstance(d, WholeFile):
        return 1, len(lines), None
    if isinstance(d, Lines):
        if not (1 <= d.start <= d.end <= len(lines)):
            raise LabelError(f"{d.file}: lines {d.start}-{d.end} out of range ({len(lines)})")
        if d.anchor and d.anchor not in lines[d.start - 1]:
            raise LabelError(f"{d.file}:{d.start} does not contain anchor {d.anchor!r}")
        return d.start, d.end, None
    raise TypeError(d)


def _span_sha(repository: str, rel: str, a: int, b: int) -> str:
    text = "\n".join(_read(repository, rel)[a - 1 : b])
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Index membership (which indexed chunks overlap each span)
# ---------------------------------------------------------------------------


def _indexed_chunks(repository: str, rel: str) -> List[Tuple[int, int, str]]:
    body = {
        "limit": 1000,
        "with_payload": ["chunk_id", "start_line", "end_line", "metadata.commit_sha"],
        "with_vector": False,
        "filter": {"must": [
            {"key": "repository", "match": {"value": repository}},
            {"key": "metadata.file_path", "match": {"value": rel}},
        ]},
    }
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        points = json.load(resp)["result"]["points"]
    out = []
    for p in points:
        pl = p["payload"]
        if pl.get("metadata", {}).get("commit_sha") != PINNED_COMMITS[repository]:
            raise LabelError(f"{repository}:{rel} indexed at a different commit")
        out.append((pl.get("start_line") or 1, pl.get("end_line") or 10**9, pl["chunk_id"]))
    return sorted(out)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def load_dev_val_tasks() -> Tuple[Dict[str, dict], Dict[str, str]]:
    """Load ONLY dev + val tasks; test task records are never read into memory."""
    splits = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    split_of = {tid: name for name in ("dev", "val") for tid in splits["splits"][name]}
    raw = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    tasks = {t["task_id"]: t for t in raw["tasks"] if t["task_id"] in split_of}
    return tasks, split_of


def build() -> RetrievalLabelSet:
    tasks, split_of = load_dev_val_tasks()
    if set(SPECS) != set(split_of):
        missing, extra = set(split_of) - set(SPECS), set(SPECS) - set(split_of)
        raise LabelError(f"spec/task mismatch: missing={sorted(missing)} extra={sorted(extra)}")

    for repository, sha in PINNED_COMMITS.items():
        if checkout_sha(repository) != sha:
            raise LabelError(
                f"{repository} must be checked out at {sha} in {repo_dir(repository)} "
                "(see docs/RETRIEVAL_LABELS.md)"
            )

    labels: List[RetrievalGroundTruth] = []
    for task_id in sorted(SPECS):
        spec, task = SPECS[task_id], tasks[task_id]
        repository = task["repository"]
        evidence: List[RequiredEvidence] = []
        for d in spec.evidence:
            a, b, symbol = resolve(repository, d)
            chunks = _indexed_chunks(repository, d.file)
            if not chunks:
                raise LabelError(f"{repository}:{d.file} is not in the index")
            overlapping = [cid for s, e, cid in chunks if s <= b and e >= a]
            evidence.append(RequiredEvidence(
                file=d.file, start_line=a, end_line=b, symbol=symbol, why=d.why,
                span_sha256=_span_sha(repository, d.file, a, b), chunk_ids=overlapping,
            ))
        for alt in spec.alternatives:
            _read(repository, alt)
            if not _indexed_chunks(repository, alt):
                raise LabelError(f"{repository}:{alt} (alternative) is not in the index")

        files = list(dict.fromkeys(e.file for e in evidence))
        symbols = list(dict.fromkeys(
            [e.symbol for e in evidence if e.symbol and isinstance_sym(spec, e.symbol)]
            + list(spec.extra_symbols)
        ))
        labels.append(RetrievalGroundTruth(
            task_id=task_id,
            split=split_of[task_id],
            repository=repository,
            commit_sha=PINNED_COMMITS[repository],
            relevant_files=files,
            alternative_files=list(spec.alternatives),
            relevant_symbols=symbols,
            required_evidence=evidence,
            expected_citations=[f"[{e.file}:L{e.start_line}-L{e.end_line}]" for e in evidence],
            label_status="flagged" if spec.flagged else "draft",
            annotator=ANNOTATOR,
            ground_truth_issue=spec.ground_truth_issue,
            notes=spec.notes,
        ))

    return RetrievalLabelSet(
        labels_version=LABELS_VERSION,
        benchmark_version=json.loads(SPLITS_PATH.read_text(encoding="utf-8"))["benchmark_version"],
        created_at=CREATED_AT,
        label_protocol="docs/RETRIEVAL_LABELS.md",
        repositories=dict(PINNED_COMMITS),
        labels=labels,
    )


def isinstance_sym(spec: LabelSpec, symbol: str) -> bool:
    """Only Python symbols (not doc headings) go into relevant_symbols."""
    return any(isinstance(d, (Sym, PyData)) and symbol in (getattr(d, "qualname", None), getattr(d, "name", None))
               for d in spec.evidence)


def render(label_set: RetrievalLabelSet) -> str:
    return json.dumps(label_set.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def load_labels(path: Path = LABELS_PATH) -> RetrievalLabelSet:
    return RetrievalLabelSet.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build MEIB dev+val retrieval labels")
    parser.add_argument("--check", action="store_true", help="fail if the labels file is stale")
    args = parser.parse_args(argv)
    rendered = render(build())
    if args.check:
        current = LABELS_PATH.read_text(encoding="utf-8") if LABELS_PATH.exists() else ""
        if current != rendered:
            print(f"{LABELS_PATH.name} is stale; run python -m benchmark.retrieval_labels")
            return 1
        print(f"{LABELS_PATH.name} is up to date")
        return 0
    LABELS_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {LABELS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
