"""
Engineering Intelligence Hub — Knowledge Graph Node IDs
=======================================================
One place for the node-ID conventions that more than one module depends on.

File nodes are keyed WITHOUT the commit: ``file:{repository}:{path}``. That is
the key GraphAugmentedRetriever builds from a retrieved chunk (its
``repository`` and ``source_path``), so a file node is only ever reachable if it
uses exactly this form. The commit is kept as the node's ``commit_sha``
property; scripts/build_graph.py checks it equals the commit indexed in Qdrant,
so one graph never mixes revisions of a repository.

Before this module the builder keyed files as ``file:{repo}:{commit}:{path}``,
the retriever never found a node, and System D silently equalled System C.
"""

from __future__ import annotations

from typing import Optional

# Source roots stripped from paths when naming modules, so that
# "src/flask/app.py" becomes "flask.app" — the name its importers use.
_SOURCE_ROOTS = ("src/", "lib/")


def normalise_path(path: str) -> str:
    """Repo-relative path with forward slashes, as stored in the vector index."""
    path = path.replace("\\", "/")
    return path[2:] if path.startswith("./") else path


def file_node_id(repository: str, path: str) -> str:
    """ID of the File node for ``path`` in ``repository`` (retriever lookup key)."""
    return f"file:{repository}:{normalise_path(path)}"


def module_name_for_path(path: str) -> Optional[str]:
    """
    Dotted import name of a Python file, or None for non-Python files.

    "src/flask/app.py" -> "flask.app"; "flask/__init__.py" -> "flask".
    """
    path = normalise_path(path)
    if not path.endswith(".py"):
        return None
    for root in _SOURCE_ROOTS:
        if path.startswith(root):
            path = path[len(root):]
            break
    path = path[: -len(".py")]
    if path.endswith("/__init__"):
        path = path[: -len("/__init__")]
    elif path == "__init__":
        return None
    return path.replace("/", ".") or None


def module_node_id(repository: str, commit: str, module_name: str) -> str:
    """ID of the Module node for a dotted module name."""
    return f"module:{repository}:{commit}:{module_name}"
