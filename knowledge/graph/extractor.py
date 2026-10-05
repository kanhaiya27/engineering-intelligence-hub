"""
Engineering Intelligence Hub — Repository Knowledge-Graph Extractor
===================================================================
Extracts the engineering knowledge graph of ONE repository at ONE pinned commit, from
the source AST and from Git history (original plan §6.2: "entities and edges extracted
from AST and history").

Nodes  Repository · File (every indexed file, code or docs) · Class · Function ·
       Method · Test (test functions/methods/classes in test files) · Commit
Edges  Repository-CONTAINS->File · File-CONTAINS->Class/Function/Test ·
       Class-CONTAINS->Method/Test · File-IMPORTS->File · Symbol-CALLS->Symbol ·
       File(test)-TESTS->File · Commit-MODIFIES->File

Rewritten 2026-10-05; the previous extractor could never feed System D:
  * node ids embedded the commit (`file:{repo}:{commit}:{path}`) while the retriever
    looks up `file:{repo}:{path}` -> no seed node was ever found
  * module names used `rstrip(".py")` (strips characters: `http.py` -> `htt`) and kept
    `src/`, so imports never resolved; relative imports were ignored
  * call targets used another id format and only the same file; methods' calls ignored
  * any path containing "test" was a test (all of `src/_pytest/` in pytest)
Every edge here connects two nodes that exist (`graph_edges_dropped` counts the rest).
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Set, Tuple

from core.logging import get_logger
from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType

logger = get_logger(__name__)


# --------------------------------------------------------------------------- ids
def repo_node_id(repo: str) -> str:
    return f"repo:{repo}"


def file_node_id(repo: str, path: str) -> str:
    """The id the graph retriever looks up for a retrieved chunk's file."""
    return f"file:{repo}:{path}"


def symbol_node_id(repo: str, path: str, qualname: str) -> str:
    return f"sym:{repo}:{path}:{qualname}"


def commit_node_id(repo: str, sha: str) -> str:
    return f"commit:{repo}:{sha}"


# --------------------------------------------------------------------------- helpers
def module_names(path: str) -> List[str]:
    """Importable dotted names of a Python file (src/ layouts give two names)."""
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return []
    parts = list(p.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return []
    names = [".".join(parts)]
    for root in ("src", "lib"):
        if parts[0] == root and len(parts) > 1:
            names.append(".".join(parts[1:]))
    return names


def is_test_file(path: str) -> bool:
    """Test files by naming convention — not "contains the word test" anywhere."""
    p = PurePosixPath(path)
    name = p.name
    if p.suffix != ".py":
        return False
    if name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in ("tests", "test", "testing") for part in p.parts[:-1])


@dataclass
class RepoGraph:
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: Dict[Tuple[str, str, str], GraphEdge] = field(default_factory=dict)
    dropped_edges: int = 0
    parse_errors: List[str] = field(default_factory=list)
    history: Dict[str, int] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, src: str, tgt: str, rel: str, **props) -> None:
        if src == tgt:
            return
        if src not in self.nodes or tgt not in self.nodes:
            self.dropped_edges += 1
            return
        key = (src, tgt, rel)
        if key not in self.edges:
            self.edges[key] = GraphEdge(src, tgt, rel, props)


class RepositoryGraphExtractor:
    """Builds the graph of one repository from its files and its Git history."""

    def __init__(self, repository: str, commit_sha: str) -> None:
        self.repo = repository
        self.commit = commit_sha

    # ----------------------------------------------------------------- public
    def extract(self, files: Iterable[Tuple[str, str]], repo_dir: Optional[Path] = None,
                max_commits: int = 500, max_files_per_commit: int = 30) -> RepoGraph:
        """files: (repo-relative path, content) for every indexed file."""
        g = RepoGraph()
        g.add_node(GraphNode(repo_node_id(self.repo), NodeLabel.REPOSITORY,
                             {"repository": self.repo, "commit_sha": self.commit, "name": self.repo}))
        files = list(files)
        for path, content in files:
            g.add_node(GraphNode(file_node_id(self.repo, path), NodeLabel.FILE, {
                "repository": self.repo, "commit_sha": self.commit, "file_path": path, "name": path,
                "line_count": len(content.splitlines()), "is_test": is_test_file(path),
            }))
            g.add_edge(repo_node_id(self.repo), file_node_id(self.repo, path), RelationshipType.CONTAINS)

        module_map: Dict[str, str] = {}
        for path, _ in files:
            for name in module_names(path):
                module_map.setdefault(name, path)

        trees: Dict[str, ast.Module] = {}
        for path, content in files:
            if not path.endswith(".py"):
                continue
            try:
                trees[path] = ast.parse(content)
            except (SyntaxError, ValueError):
                g.parse_errors.append(path)
                continue
            self._symbols(g, path, trees[path])

        top_level: Dict[str, Set[str]] = {
            p: {n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            for p, t in trees.items()
        }
        for path, tree in trees.items():
            imported = self._imports(g, path, tree, module_map, top_level)
            self._calls(g, path, tree, imported, top_level)

        if repo_dir is not None:
            self._history(g, repo_dir, {p for p, _ in files}, max_commits, max_files_per_commit)
        return g

    # ----------------------------------------------------------------- AST
    def _symbol_node(self, path: str, qualname: str, node: ast.AST, label: str) -> GraphNode:
        return GraphNode(symbol_node_id(self.repo, path, qualname), label, {
            "repository": self.repo, "commit_sha": self.commit, "file_path": path,
            "symbol_name": qualname, "name": qualname,
            "start_line": min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]),
            "end_line": getattr(node, "end_lineno", node.lineno),
        })

    def _symbols(self, g: RepoGraph, path: str, tree: ast.Module) -> None:
        test_file = is_test_file(path)
        fid = file_node_id(self.repo, path)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                label = NodeLabel.TEST if test_file and node.name.startswith("Test") else NodeLabel.CLASS
                g.add_node(self._symbol_node(path, node.name, node, label))
                cid = symbol_node_id(self.repo, path, node.name)
                g.add_edge(fid, cid, RelationshipType.CONTAINS)
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        q = f"{node.name}.{m.name}"
                        mlabel = NodeLabel.TEST if test_file and m.name.startswith("test") else NodeLabel.METHOD
                        g.add_node(self._symbol_node(path, q, m, mlabel))
                        g.add_edge(cid, symbol_node_id(self.repo, path, q), RelationshipType.CONTAINS)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                label = NodeLabel.TEST if test_file and node.name.startswith("test") else NodeLabel.FUNCTION
                g.add_node(self._symbol_node(path, node.name, node, label))
                g.add_edge(fid, symbol_node_id(self.repo, path, node.name), RelationshipType.CONTAINS)

    def _resolve_module(self, dotted: str, module_map: Dict[str, str]) -> Optional[str]:
        parts = dotted.split(".")
        while parts:  # a.b.c -> a.b -> a: the longest prefix that is a file in this repo
            hit = module_map.get(".".join(parts))
            if hit:
                return hit
            parts = parts[:-1]
        return None

    def _package_of(self, path: str) -> List[str]:
        names = module_names(path)
        if not names:
            return []
        dotted = names[-1].split(".")  # src-stripped name when available
        return dotted if path.endswith("__init__.py") else dotted[:-1]

    def _imports(self, g: RepoGraph, path: str, tree: ast.Module, module_map: Dict[str, str],
                 top_level: Dict[str, Set[str]]) -> Dict[str, Tuple[str, Optional[str]]]:
        """IMPORTS (+ TESTS for test files) edges; returns local name -> (target file, symbol)."""
        fid = file_node_id(self.repo, path)
        imported: Dict[str, Tuple[str, Optional[str]]] = {}
        targets: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = self._resolve_module(alias.name, module_map)
                    if target:
                        targets.add(target)
                        imported[alias.asname or alias.name.split(".")[0]] = (target, None)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = self._package_of(path)
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    module = ".".join(base + ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                for alias in node.names:
                    sub = self._resolve_module(f"{module}.{alias.name}", module_map) if module else None
                    target = sub if sub and sub != self._resolve_module(module, module_map) else \
                        self._resolve_module(module, module_map)
                    if not target:
                        continue
                    targets.add(target)
                    symbol = alias.name if alias.name in top_level.get(target, set()) else None
                    imported[alias.asname or alias.name] = (target, symbol)
        for target in targets:
            if target == path:
                continue
            g.add_edge(fid, file_node_id(self.repo, target), RelationshipType.IMPORTS)
            if is_test_file(path) and not is_test_file(target):
                g.add_edge(fid, file_node_id(self.repo, target), RelationshipType.TESTS)
        return imported

    def _calls(self, g: RepoGraph, path: str, tree: ast.Module,
               imported: Dict[str, Tuple[str, Optional[str]]], top_level: Dict[str, Set[str]]) -> None:
        local = top_level.get(path, set())
        scopes: List[Tuple[str, Optional[str], ast.AST]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes.append((node.name, None, node))
            elif isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        scopes.append((f"{node.name}.{m.name}", node.name, m))
        class_methods = {q.split(".")[0]: set() for q, c, _ in scopes if c}
        for q, c, _ in scopes:
            if c:
                class_methods[c].add(q.split(".", 1)[1])

        for qualname, cls, fn in scopes:
            src = symbol_node_id(self.repo, path, qualname)
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                target = None
                f = call.func
                if isinstance(f, ast.Name):
                    if f.id in local:
                        target = symbol_node_id(self.repo, path, f.id)
                    elif f.id in imported and imported[f.id][1]:
                        t_path, t_sym = imported[f.id]
                        target = symbol_node_id(self.repo, t_path, t_sym)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    owner = f.value.id
                    if owner in ("self", "cls") and cls and f.attr in class_methods.get(cls, set()):
                        target = symbol_node_id(self.repo, path, f"{cls}.{f.attr}")
                    elif owner in imported and imported[owner][1] is None:
                        t_path = imported[owner][0]
                        if f.attr in top_level.get(t_path, set()):
                            target = symbol_node_id(self.repo, t_path, f.attr)
                if target and target != src:
                    g.add_edge(src, target, RelationshipType.CALLS, line=call.lineno)

    # ----------------------------------------------------------------- history
    def _history(self, g: RepoGraph, repo_dir: Path, known_files: Set[str], max_commits: int,
                 max_files_per_commit: int) -> None:
        """Commit-MODIFIES->File for the last `max_commits` non-merge commits up to the pin.

        Bulk commits touching more than `max_files_per_commit` indexed files (mass
        reformatting, licence headers) are skipped: they would link unrelated files.
        """
        fmt = "%x1e%H%x1f%aI%x1f%s"
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "--no-merges", f"-n{max_commits}", f"--format={fmt}",
             "--name-only", self.commit],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
        used = skipped_bulk = 0
        for record in out.split("\x1e")[1:]:
            header, *paths = record.strip("\n").split("\n")
            sha, date, subject = (header.split("\x1f") + ["", ""])[:3]
            touched = sorted({p.strip() for p in paths if p.strip() in known_files})
            if not touched:
                continue
            if len(touched) > max_files_per_commit:
                skipped_bulk += 1
                continue
            cid = commit_node_id(self.repo, sha)
            g.add_node(GraphNode(cid, NodeLabel.COMMIT, {
                "repository": self.repo, "commit_sha": sha, "name": subject[:200], "date": date,
                "files_changed": len(touched),
            }))
            for p in touched:
                g.add_edge(cid, file_node_id(self.repo, p), RelationshipType.MODIFIES)
            used += 1
        g.history = {"commits_scanned": max_commits, "commits_linked": used, "bulk_commits_skipped": skipped_bulk,
                     "max_files_per_commit": max_files_per_commit}


# Backwards-compatible name: the per-file extractor was replaced by the repository one.
ASTGraphExtractor = RepositoryGraphExtractor
