"""
OKF producer: turn EIH's knowledge sources into an OKF v0.2 bundle, deterministically.

Every concept is extracted mechanically from a source that can be checked (a file at a
pinned commit, a frozen API contract, a project document). No LLM writes here, so nothing
unverified is presented as established knowledge; agent-written knowledge only enters a
bundle through a human-approved proposal (`collaboration.py`).

Produced concepts carry (OKF §5):
  * ``generated: {by: eih_okf_producer/<version>, at}``,
  * ``sources`` naming the exact file at the exact commit,
  * no ``verified`` (the tier is "unverified" until a person or process checks them),
  * ``resource`` = the canonical URL of the asset.

Layout of the produced bundle::

    repositories/<repo_id>.md                    type: Repository
    code/<repo_id>/<path without .py>.md         type: Python Module
    eih/api/<operation>.md                       type: API Endpoint   (frozen contract v1)
    eih/docs/<name>.md                           type: Project Document

A re-run rewrites only concepts it owns (``generated.by`` starting with the producer
name) and never touches a concept a person or an approved proposal wrote.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from knowledge.graph.extractor import is_test_file, module_names
from knowledge.okf.bundle import OKFBundle
from knowledge.okf.document import OKFDocument, utc_now_iso

PRODUCER = "eih_okf_producer"
PRODUCER_VERSION = "0.1"
ACTOR = f"{PRODUCER}/{PRODUCER_VERSION}"

_EXCLUDED_DIRS = ("docs_src", "doc", "docs", "scripts", "examples", "benchmarks")
_SEG_CLEAN = re.compile(r"[^A-Za-z0-9_.\-]")


def _seg(s: str) -> str:
    s = _SEG_CLEAN.sub("-", s)
    return s if s and (s[0].isalnum() or s[0] == "_") else f"_{s}"


def _first_paragraph(doc: Optional[str], limit: int = 240) -> str:
    if not doc:
        return ""
    para = doc.strip().split("\n\n", 1)[0]
    para = " ".join(para.split())
    return para if len(para) <= limit else para[: limit - 1].rstrip() + "…"


@dataclass
class ProducedConcept:
    concept_id: str
    frontmatter: Dict[str, Any]
    body: str


@dataclass
class ProduceReport:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    skipped_not_owned: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"written": len(self.written), "unchanged": len(self.unchanged),
                "skipped_not_owned": self.skipped_not_owned, "errors": self.errors}


# ---------------------------------------------------------------------- Python modules


def _module_summary(source: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    tree = ast.parse(source)
    classes, functions, imports = [], [], []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({"name": node.name, "lines": (node.lineno, node.end_lineno),
                            "doc": _first_paragraph(ast.get_docstring(node), 160),
                            "bases": [ast.unparse(b) for b in node.bases], "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "lines": (node.lineno, node.end_lineno),
                              "doc": _first_paragraph(ast.get_docstring(node), 160)})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
            # `from pkg import mod` may import a submodule: keep pkg.mod as a candidate
            # (it only becomes a link if such a module exists in the repository).
            imports.extend(f"{node.module}.{a.name}" for a in node.names if a.name != "*")
    return _first_paragraph(ast.get_docstring(tree)), classes, functions, sorted(set(imports))


def produce_repository(entry: Dict[str, Any], repo_dir: Path, now: str) -> List[ProducedConcept]:
    """Repository concept + one Python Module concept per non-test source module."""
    repo_id, owner, name = entry["repo_id"], entry["owner"], entry["name"]
    sha = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True).stdout.strip()
    if entry.get("selected_commit") and sha != entry["selected_commit"]:
        raise RuntimeError(f"{repo_id}: checkout {sha} != pinned {entry['selected_commit']}")
    # -z: raw NUL-separated paths (without it git quotes non-ASCII names).
    files = [f for f in subprocess.run(["git", "-C", str(repo_dir), "ls-files", "-z", "*.py"], capture_output=True,
                                       check=True).stdout.decode("utf-8").split("\0") if f]
    files = [f for f in files if not is_test_file(f) and PurePosixPath(f).parts[0] not in _EXCLUDED_DIRS]
    blob = f"https://github.com/{owner}/{name}/blob/{sha}"

    by_module: Dict[str, str] = {}
    for f in files:
        for m in module_names(f):
            by_module.setdefault(m, f)

    def cid(path: str) -> str:
        # Keep the .py suffix in the id: `index.py` / `log.py` modules would otherwise map
        # to the reserved index.md / log.md (§3.1), and `pkg.py` would collide with `pkg/`.
        return "code/" + _seg(repo_id) + "/" + "/".join(_seg(p) for p in PurePosixPath(path).parts)

    out: List[ProducedConcept] = []
    module_rows = []
    for f in sorted(files):
        try:
            source = (repo_dir / f).read_text(encoding="utf-8", errors="replace")
            doc, classes, functions, imports = _module_summary(source)
        except (SyntaxError, OSError, ValueError):
            continue  # not parseable as Python 3 / not on disk: no concept rather than a wrong one
        dotted = module_names(f)[-1] if module_names(f) else f
        body = [f"# Module `{dotted}`", "",
                f"Source: [`{f}`]({blob}/{f}) at commit `{sha[:12]}` of "
                f"[{owner}/{name}](/repositories/{_seg(repo_id)}.md).", ""]
        if doc:
            body += [doc, ""]
        if classes:
            body += ["# Classes", "", "| Class | Lines | Bases | Summary |", "|---|---|---|---|"]
            for c in classes:
                body.append(f"| `{c['name']}` | [{c['lines'][0]}-{c['lines'][1]}]({blob}/{f}#L{c['lines'][0]}-L{c['lines'][1]}) "
                            f"| {', '.join(f'`{b}`' for b in c['bases']) or '-'} | {c['doc'].replace('|', '/') or '-'} |")
            body.append("")
        if functions:
            body += ["# Functions", "", "| Function | Lines | Summary |", "|---|---|---|"]
            for fn in functions:
                body.append(f"| `{fn['name']}()` | [{fn['lines'][0]}-{fn['lines'][1]}]({blob}/{f}#L{fn['lines'][0]}-L{fn['lines'][1]}) "
                            f"| {fn['doc'].replace('|', '/') or '-'} |")
            body.append("")
        internal = sorted({by_module[i] for i in imports if i in by_module and by_module[i] != f})
        if internal:
            body += ["# Depends on", ""] + [f"* [{module_names(p)[-1]}](/{cid(p)}.md)" for p in internal] + [""]
        fm = {
            "type": "Python Module",
            "title": dotted,
            "description": doc or f"Python module {dotted} of {owner}/{name}.",
            "resource": f"{blob}/{f}",
            "tags": [repo_id, "python", "module"],
            "generated": {"by": ACTOR, "at": now},
            "sources": [{"id": "source", "resource": f"{blob}/{f}", "title": f"{owner}/{name}:{f}@{sha[:12]}"}],
            "eih": {"repository": f"{owner}/{name}", "commit": sha, "path": f,
                    "classes": len(classes), "functions": len(functions)},
        }
        out.append(ProducedConcept(cid(f), fm, "\n".join(body).rstrip() + "\n"))
        module_rows.append((dotted, cid(f), fm["description"]))

    repo_body = [f"# {owner}/{name}", "", f"Pinned at tag `{entry.get('selected_tag')}`, commit `{sha}`.", ""]
    if entry.get("notes") or entry.get("description"):
        repo_body += [str(entry.get("notes") or entry.get("description")).strip(), ""]
    repo_body += ["# Modules", ""] + [f"* [{d}](/{c}.md) - {desc}" for d, c, desc in module_rows] + [""]
    out.append(ProducedConcept(f"repositories/{_seg(repo_id)}", {
        "type": "Repository",
        "title": f"{owner}/{name}",
        "description": f"{entry.get('language', '')} repository {owner}/{name} at {entry.get('selected_tag')}, "
                       f"{len(module_rows)} source modules.".strip(),
        "resource": f"https://github.com/{owner}/{name}/tree/{sha}",
        "tags": [repo_id, str(entry.get("language", "")).lower(), "repository"],
        "generated": {"by": ACTOR, "at": now},
        "sources": [{"id": "registry", "resource": "datasets/registry.yaml", "title": "EIH dataset registry"}],
        "eih": {"repository": f"{owner}/{name}", "commit": sha, "wave": entry.get("wave")},
    }, "\n".join(repo_body)))
    return out


# ---------------------------------------------------------------------- EIH API + docs


def produce_api_contract(openapi_path: Path, now: str) -> List[ProducedConcept]:
    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    version = spec.get("info", {}).get("version", "")
    out = []
    for path, ops in sorted(spec.get("paths", {}).items()):
        for method, op in sorted(ops.items()):
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            op_id = op.get("operationId") or f"{method}_{path}"
            body = [f"# `{method.upper()} {path}`", "", op.get("description") or op.get("summary") or "", ""]
            req = op.get("requestBody", {}).get("content", {})
            if req:
                body += ["# Request", ""] + [f"* `{ct}`: `{(v.get('schema') or {}).get('$ref', '').rsplit('/', 1)[-1]}`"
                                             for ct, v in req.items()] + [""]
            body += ["# Responses", "", "| Status | Description |", "|---|---|"]
            for code, r in sorted(op.get("responses", {}).items()):
                body.append(f"| {code} | {(r.get('description') or '').replace('|', '/')} |")
            out.append(ProducedConcept(f"eih/api/{_seg(op_id)}", {
                "type": "API Endpoint",
                "title": f"{method.upper()} {path}",
                "description": _first_paragraph(op.get("summary") or op.get("description") or f"{method.upper()} {path}"),
                "tags": ["eih", "api", f"contract-{version}"],
                "generated": {"by": ACTOR, "at": now},
                "sources": [{"id": "contract", "resource": "docs/api/openapi-v1.json",
                             "title": f"EIH API contract {version}"}],
            }, "\n".join(body).rstrip() + "\n"))
    return out


def produce_project_docs(paths: Iterable[Path], project_root: Path, now: str) -> List[ProducedConcept]:
    out = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        heading = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("# ")), p.stem)
        first = next((l.strip() for l in text.split("\n\n")[1:] if l.strip() and not l.startswith(("#", "|", ">", "-"))), "")
        rel = p.relative_to(project_root).as_posix()
        out.append(ProducedConcept(f"eih/docs/{_seg(p.stem)}", {
            "type": "Project Document",
            "title": heading,
            "description": _first_paragraph(first, 200) or heading,
            "resource": rel,
            "tags": ["eih", "documentation"],
            "generated": {"by": ACTOR, "at": now},
            "sources": [{"id": "file", "resource": rel, "title": rel}],
        }, text if text.endswith("\n") else text + "\n"))
    return out


# ---------------------------------------------------------------------- write


def _comparable(fm: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in fm.items() if k != "generated"}


def write_produced(bundle: OKFBundle, concepts: List[ProducedConcept]) -> ProduceReport:
    """Write produced concepts; keep untouched concepts' `generated.at` when nothing changed;
    never overwrite a concept that the producer does not own."""
    rep = ProduceReport()
    for pc in concepts:
        cur = bundle.get(pc.concept_id)
        if cur is not None:
            owner = cur.doc.generated_by or ""
            if not owner.startswith(PRODUCER + "/"):
                rep.skipped_not_owned.append(pc.concept_id)
                continue
            if _comparable(cur.doc.frontmatter) == _comparable(pc.frontmatter) and cur.doc.body == pc.body:
                rep.unchanged.append(pc.concept_id)
                continue
        try:
            bundle.write_concept(pc.concept_id, OKFDocument(frontmatter=pc.frontmatter, body=pc.body))
            rep.written.append(pc.concept_id)
        except Exception as exc:  # noqa: BLE001 - report every failure
            rep.errors.append({"concept_id": pc.concept_id, "error": str(exc)})
    return rep


def produce_eih_bundle(bundle_dir: Path, project_root: Path, registry_path: Path, cache_dir: Path,
                       wave: int = 1, docs: Optional[List[Path]] = None) -> Tuple[OKFBundle, ProduceReport]:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle = OKFBundle(bundle_dir)
    now = utc_now_iso()
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    concepts: List[ProducedConcept] = []
    for e in registry["repositories"]:
        if e.get("wave") == wave and (cache_dir / e["repo_id"] / ".git").exists():
            concepts += produce_repository(e, cache_dir / e["repo_id"], now)
    contract = project_root / "docs" / "api" / "openapi-v1.json"
    if contract.exists():
        concepts += produce_api_contract(contract, now)
    concepts += produce_project_docs(docs or [], project_root, now)
    rep = write_produced(bundle, concepts)
    if rep.written:
        bundle.append_log([f"**Update**: `{ACTOR}` wrote {len(rep.written)} concepts "
                           f"({len(rep.unchanged)} unchanged) from wave-{wave} repositories, the API contract "
                           f"and {len(docs or [])} project documents."])
    bundle.regenerate_indexes()
    bundle.reload()
    return bundle, rep
