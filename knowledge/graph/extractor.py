"""
Engineering Intelligence Hub — AST Graph Entity & Relationship Extractor
========================================================================
Extracts code entities (Modules, Classes, Functions, Methods, Tests) and their
syntactic relationships (CONTAINS, IMPORTS, DEPENDS_ON, CALLS) from Python AST.

Edges point at the IDs the target nodes really have:
  * IMPORTS / DEPENDS_ON target ``module:{repo}:{commit}:{dotted name}``, where a
    file's dotted name drops a ``src/`` or ``lib/`` root ("src/flask/app.py" ->
    "flask.app"), so an import of ``flask.app`` lands on that file's module.
    Relative imports are resolved against the importing package. Imports of
    modules outside the repository have no node; EngineeringGraphBuilder drops
    those edges and counts them.
  * CALLS is emitted only when the callee resolves inside the same file: a bare
    name to a top-level function, ``self.x`` / ``cls.x`` to a method of the same
    class. Cross-file calls need type information and are not guessed.
"""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple, Union

from core.logging import get_logger
from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.graph.ids import file_node_id, module_name_for_path, module_node_id, normalise_path
from knowledge.schemas.artifacts import SourceFile

logger = get_logger(__name__)

_FunctionDef = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def is_test_path(file_path: str) -> bool:
    """True for test files: a ``test``/``tests``/``testing`` directory or a test_*.py / *_test.py file."""
    parts = normalise_path(file_path).lower().split("/")
    filename = parts[-1]
    if filename.startswith("test_") or filename.endswith("_test.py") or filename == "conftest.py":
        return True
    return any(part in {"test", "tests", "testing"} for part in parts[:-1])


def _resolve_import_from(item: ast.ImportFrom, module_name: str, is_package: bool) -> Optional[str]:
    """Absolute dotted name for an ImportFrom, resolving ``from . import x`` style imports."""
    if item.level == 0:
        return item.module
    package = module_name.split(".") if is_package else module_name.split(".")[:-1]
    up = item.level - 1
    if up > len(package):
        return None
    base = package[: len(package) - up]
    if item.module:
        base = base + item.module.split(".")
    return ".".join(base) or None


class ASTGraphExtractor:
    """
    Parses Python source code AST to generate graph nodes and relationships
    with strict provenance preservation.
    """

    def extract(self, source_file: SourceFile) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Extract code entity nodes and relationships from a SourceFile.

        Parameters
        ----------
        source_file : SourceFile
            The ingested source code artifact.

        Returns
        -------
        Tuple[List[GraphNode], List[GraphEdge]]
            Extracted graph nodes and directed relationships.
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        repo = source_file.repository
        commit = getattr(source_file, "commit_sha", None) or "latest"
        file_path = normalise_path(source_file.source_path or source_file.artifact_id)
        code = getattr(source_file, "content", None) or source_file.raw_content or ""

        # 1. File Node
        file_id = file_node_id(repo, file_path)
        file_node = GraphNode(
            node_id=file_id,
            label=NodeLabel.FILE,
            properties={
                "repository": repo,
                "commit_sha": commit,
                "file_path": file_path,
                "artifact_id": source_file.artifact_id,
                "artifact_type": "source_code",
                "line_count": source_file.line_count or len(code.splitlines()),
                "language": source_file.language,
            },
        )
        nodes.append(file_node)

        # Non-Python files: return file node
        module_name = module_name_for_path(file_path)
        if module_name is None:
            return nodes, edges

        try:
            tree = ast.parse(code, filename=file_path)
        except (SyntaxError, ValueError) as e:
            logger.debug(f"Cannot parse {file_path} for graph extraction: {e}")
            return nodes, edges

        # 2. Module Node
        module_id = module_node_id(repo, commit, module_name)
        nodes.append(GraphNode(
            node_id=module_id,
            label=NodeLabel.MODULE,
            properties={
                "repository": repo,
                "commit_sha": commit,
                "file_path": file_path,
                "symbol_name": module_name,
                "artifact_id": source_file.artifact_id,
            },
        ))
        edges.append(GraphEdge(
            source_id=file_id,
            target_id=module_id,
            relationship=RelationshipType.CONTAINS,
        ))

        is_test_file = is_test_path(file_path)
        is_package = file_path.endswith("__init__.py")

        # 3. Imports anywhere in the file (incl. inside try/except and TYPE_CHECKING blocks)
        imported: Dict[str, int] = {}
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imported.setdefault(alias.name, item.lineno)
            elif isinstance(item, ast.ImportFrom):
                target = _resolve_import_from(item, module_name, is_package)
                if not target:
                    continue
                imported.setdefault(target, item.lineno)
                # "from pkg import sub" may name a submodule; the builder keeps
                # this edge only if pkg.sub is a module in the repository.
                for alias in item.names:
                    if alias.name != "*":
                        imported.setdefault(f"{target}.{alias.name}", item.lineno)
        for target, lineno in imported.items():
            if target == module_name:
                continue
            target_id = module_node_id(repo, commit, target)
            edges.append(GraphEdge(
                source_id=module_id,
                target_id=target_id,
                relationship=RelationshipType.IMPORTS,
                properties={"line_start": lineno},
            ))
            edges.append(GraphEdge(
                source_id=module_id,
                target_id=target_id,
                relationship=RelationshipType.DEPENDS_ON,
            ))

        def symbol_node(node_id: str, label: str, item: ast.AST, symbol: str, **extra) -> GraphNode:
            return GraphNode(
                node_id=node_id,
                label=label,
                properties={
                    "repository": repo,
                    "commit_sha": commit,
                    "file_path": file_path,
                    "symbol_name": symbol,
                    "start_line": item.lineno,
                    "end_line": getattr(item, "end_lineno", item.lineno),
                    "artifact_id": source_file.artifact_id,
                    **extra,
                },
            )

        # 4. Top-level classes, methods and functions
        functions: Dict[str, str] = {}                      # name -> node_id
        methods: Dict[str, Dict[str, str]] = {}             # class -> name -> node_id
        bodies: List[Tuple[str, Optional[str], _FunctionDef]] = []  # (node_id, class, def)

        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                class_id = f"class:{repo}:{commit}:{file_path}:{item.name}"
                nodes.append(symbol_node(class_id, NodeLabel.CLASS, item, item.name))
                edges.append(GraphEdge(
                    source_id=module_id,
                    target_id=class_id,
                    relationship=RelationshipType.CONTAINS,
                ))
                methods[item.name] = {}
                for class_item in item.body:
                    if isinstance(class_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_id = (
                            f"method:{repo}:{commit}:{file_path}:{item.name}:"
                            f"{class_item.name}:{class_item.lineno}"
                        )
                        label = (
                            NodeLabel.TEST
                            if (is_test_file or class_item.name.startswith("test_"))
                            else NodeLabel.METHOD
                        )
                        nodes.append(symbol_node(
                            method_id, label, class_item, f"{item.name}.{class_item.name}",
                            class_name=item.name,
                            is_async=isinstance(class_item, ast.AsyncFunctionDef),
                        ))
                        edges.append(GraphEdge(
                            source_id=class_id,
                            target_id=method_id,
                            relationship=RelationshipType.CONTAINS,
                        ))
                        # Last definition wins, as at runtime (e.g. property setters).
                        methods[item.name][class_item.name] = method_id
                        bodies.append((method_id, item.name, class_item))

            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_id = f"func:{repo}:{commit}:{file_path}:{item.name}:{item.lineno}"
                label = (
                    NodeLabel.TEST
                    if (is_test_file or item.name.startswith("test_"))
                    else NodeLabel.FUNCTION
                )
                nodes.append(symbol_node(
                    func_id, label, item, item.name,
                    is_async=isinstance(item, ast.AsyncFunctionDef),
                ))
                edges.append(GraphEdge(
                    source_id=module_id,
                    target_id=func_id,
                    relationship=RelationshipType.CONTAINS,
                ))
                functions[item.name] = func_id
                bodies.append((func_id, None, item))

        # 5. Calls that resolve inside this file
        for caller_id, class_name, definition in bodies:
            seen: Set[str] = set()
            for sub_node in ast.walk(definition):
                if not isinstance(sub_node, ast.Call):
                    continue
                func = sub_node.func
                target_id: Optional[str] = None
                callee: Optional[str] = None
                if isinstance(func, ast.Name):
                    callee = func.id
                    target_id = functions.get(callee)
                elif (
                    isinstance(func, ast.Attribute)
                    and class_name is not None
                    and isinstance(func.value, ast.Name)
                    and func.value.id in {"self", "cls"}
                ):
                    callee = func.attr
                    target_id = methods.get(class_name, {}).get(callee)
                if target_id is None or target_id == caller_id or target_id in seen:
                    continue
                seen.add(target_id)
                edges.append(GraphEdge(
                    source_id=caller_id,
                    target_id=target_id,
                    relationship=RelationshipType.CALLS,
                    properties={"callee_name": callee, "line_start": sub_node.lineno},
                ))

        return nodes, edges
