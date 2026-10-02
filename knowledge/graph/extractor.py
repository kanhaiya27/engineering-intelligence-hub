"""
Engineering Intelligence Hub — AST Graph Entity & Relationship Extractor
========================================================================
Extracts code entities (Modules, Classes, Functions, Methods, Tests) and their
syntactic relationships (CONTAINS, IMPORTS, CALLS, TESTED_BY) from Python AST.
"""

from __future__ import annotations

import ast
from typing import List, Tuple

from core.logging import get_logger
from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.schemas.artifacts import SourceFile

logger = get_logger(__name__)


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
        file_path = source_file.source_path or source_file.artifact_id
        code = getattr(source_file, "content", None) or source_file.raw_content or ""

        # 1. File Node
        file_node_id = f"file:{repo}:{commit}:{file_path}"
        file_node = GraphNode(
            node_id=file_node_id,
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
        if not (file_path.endswith(".py") or source_file.language == "python"):
            return nodes, edges

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error parsing {file_path} for graph extraction: {e}")
            return nodes, edges

        # 2. Module Node
        module_name = file_path.replace("/", ".").replace("\\", ".").rstrip(".py")
        module_node_id = f"module:{repo}:{commit}:{module_name}"
        module_node = GraphNode(
            node_id=module_node_id,
            label=NodeLabel.MODULE,
            properties={
                "repository": repo,
                "commit_sha": commit,
                "file_path": file_path,
                "symbol_name": module_name,
                "artifact_id": source_file.artifact_id,
            },
        )
        nodes.append(module_node)
        edges.append(GraphEdge(
            source_id=file_node_id,
            target_id=module_node_id,
            relationship=RelationshipType.CONTAINS,
        ))

        is_test_file = "test" in file_path.lower() or file_path.startswith("tests/")

        # 3. Traverse Top-Level AST Nodes
        for item in tree.body:
            # Imports
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imported_mod_id = f"module:{repo}:{commit}:{alias.name}"
                    edges.append(GraphEdge(
                        source_id=module_node_id,
                        target_id=imported_mod_id,
                        relationship=RelationshipType.IMPORTS,
                        properties={"line_start": item.lineno},
                    ))
                    edges.append(GraphEdge(
                        source_id=module_node_id,
                        target_id=imported_mod_id,
                        relationship=RelationshipType.DEPENDS_ON,
                    ))

            elif isinstance(item, ast.ImportFrom):
                if item.module:
                    imported_mod_id = f"module:{repo}:{commit}:{item.module}"
                    edges.append(GraphEdge(
                        source_id=module_node_id,
                        target_id=imported_mod_id,
                        relationship=RelationshipType.IMPORTS,
                        properties={"line_start": item.lineno},
                    ))
                    edges.append(GraphEdge(
                        source_id=module_node_id,
                        target_id=imported_mod_id,
                        relationship=RelationshipType.DEPENDS_ON,
                    ))

            # Classes
            elif isinstance(item, ast.ClassDef):
                class_node_id = f"class:{repo}:{commit}:{file_path}:{item.name}"
                class_node = GraphNode(
                    node_id=class_node_id,
                    label=NodeLabel.CLASS,
                    properties={
                        "repository": repo,
                        "commit_sha": commit,
                        "file_path": file_path,
                        "symbol_name": item.name,
                        "start_line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "artifact_id": source_file.artifact_id,
                    },
                )
                nodes.append(class_node)
                edges.append(GraphEdge(
                    source_id=module_node_id,
                    target_id=class_node_id,
                    relationship=RelationshipType.CONTAINS,
                ))

                # Methods within class
                for class_item in item.body:
                    if isinstance(class_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_node_id = f"method:{repo}:{commit}:{file_path}:{item.name}:{class_item.name}:{class_item.lineno}"
                        label = NodeLabel.TEST if (is_test_file or class_item.name.startswith("test_")) else NodeLabel.METHOD
                        method_node = GraphNode(
                            node_id=method_node_id,
                            label=label,
                            properties={
                                "repository": repo,
                                "commit_sha": commit,
                                "file_path": file_path,
                                "symbol_name": f"{item.name}.{class_item.name}",
                                "class_name": item.name,
                                "start_line": class_item.lineno,
                                "end_line": getattr(class_item, "end_lineno", class_item.lineno),
                                "is_async": isinstance(class_item, ast.AsyncFunctionDef),
                                "artifact_id": source_file.artifact_id,
                            },
                        )
                        nodes.append(method_node)
                        edges.append(GraphEdge(
                            source_id=class_node_id,
                            target_id=method_node_id,
                            relationship=RelationshipType.CONTAINS,
                        ))

            # Top-level Functions
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_node_id = f"func:{repo}:{commit}:{file_path}:{item.name}:{item.lineno}"
                label = NodeLabel.TEST if (is_test_file or item.name.startswith("test_")) else NodeLabel.FUNCTION
                func_node = GraphNode(
                    node_id=func_node_id,
                    label=label,
                    properties={
                        "repository": repo,
                        "commit_sha": commit,
                        "file_path": file_path,
                        "symbol_name": item.name,
                        "start_line": item.lineno,
                        "end_line": getattr(item, "end_lineno", item.lineno),
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "artifact_id": source_file.artifact_id,
                    },
                )
                nodes.append(func_node)
                edges.append(GraphEdge(
                    source_id=module_node_id,
                    target_id=func_node_id,
                    relationship=RelationshipType.CONTAINS,
                ))

                # Function calls within function
                for sub_node in ast.walk(item):
                    if isinstance(sub_node, ast.Call):
                        callee_name = None
                        if isinstance(sub_node.func, ast.Name):
                            callee_name = sub_node.func.id
                        elif isinstance(sub_node.func, ast.Attribute):
                            callee_name = sub_node.func.attr

                        if callee_name and len(callee_name) > 2 and not callee_name.startswith("__"):
                            target_call_id = f"func:{repo}:{commit}:{file_path}:{callee_name}"
                            edges.append(GraphEdge(
                                source_id=func_node_id,
                                target_id=target_call_id,
                                relationship=RelationshipType.CALLS,
                                properties={"callee_name": callee_name},
                            ))

        return nodes, edges
