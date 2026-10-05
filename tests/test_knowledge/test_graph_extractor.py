"""Repository knowledge-graph extractor: ids the retriever can find, resolved imports/calls/tests, Git history."""

from __future__ import annotations

import subprocess

import pytest

from knowledge.graph.base import NodeLabel, RelationshipType as R
from knowledge.graph.extractor import (
    RepositoryGraphExtractor,
    file_node_id,
    is_test_file,
    module_names,
    symbol_node_id,
)

REPO = "acme/pkg"
FILES = [
    ("src/pkg/__init__.py", "from .api import handle\n"),
    ("src/pkg/core.py",
     "def helper(x):\n    return x\n\n\nclass Engine:\n    def step(self):\n        return 1\n\n"
     "    def run(self):\n        self.step()\n        return helper(2)\n"),
    ("src/pkg/api.py",
     "from .core import helper, Engine\nimport pkg.core as c\n\n\ndef handle():\n    helper(1)\n"
     "    c.helper(3)\n    return Engine()\n"),
    ("src/pkg/http.py", "def get():\n    return 'ok'\n"),
    ("tests/test_api.py", "from pkg.api import handle\n\n\ndef test_handle():\n    assert handle()\n"),
    ("docs/index.md", "# Docs\n\nHello.\n"),
]


@pytest.fixture(scope="module")
def graph():
    return RepositoryGraphExtractor(REPO, "abc123").extract(FILES)


def edges(g, rel):
    return {(s, t) for (s, t, r) in g.edges if r == rel}


def test_module_names_handle_src_layout_and_do_not_strip_characters():
    assert module_names("src/flask/http.py") == ["src.flask.http", "flask.http"]  # old code gave "...htt"
    assert module_names("src/pkg/__init__.py") == ["src.pkg", "pkg"]
    assert module_names("docs/index.md") == []


@pytest.mark.parametrize("path,expected", [
    ("tests/test_api.py", True), ("testing/python/collect.py", True), ("src/conftest.py", True),
    ("src/_pytest/python.py", False), ("src/flask/testing.py", False), ("docs/test.rst", False),
])
def test_test_files_by_convention_not_substring(path, expected):
    assert is_test_file(path) is expected


def test_ids_have_no_commit_so_the_retriever_finds_them(graph):
    assert file_node_id(REPO, "src/pkg/core.py") == "file:acme/pkg:src/pkg/core.py"
    assert file_node_id(REPO, "src/pkg/core.py") in graph.nodes
    assert file_node_id(REPO, "docs/index.md") in graph.nodes, "every indexed file gets a node, docs too"
    assert graph.nodes[file_node_id(REPO, "src/pkg/core.py")].properties["commit_sha"] == "abc123"


def test_relative_absolute_and_aliased_imports_resolve_to_files(graph):
    f = lambda p: file_node_id(REPO, p)  # noqa: E731
    imports = edges(graph, R.IMPORTS)
    assert (f("src/pkg/api.py"), f("src/pkg/core.py")) in imports
    assert (f("src/pkg/__init__.py"), f("src/pkg/api.py")) in imports
    assert (f("tests/test_api.py"), f("src/pkg/api.py")) in imports
    assert edges(graph, R.TESTS) == {(f("tests/test_api.py"), f("src/pkg/api.py"))}


def test_calls_resolve_across_files_and_to_methods(graph):
    s = lambda p, q: symbol_node_id(REPO, p, q)  # noqa: E731
    calls = edges(graph, R.CALLS)
    assert (s("src/pkg/api.py", "handle"), s("src/pkg/core.py", "helper")) in calls
    assert (s("src/pkg/core.py", "Engine.run"), s("src/pkg/core.py", "Engine.step")) in calls
    assert (s("src/pkg/core.py", "Engine.run"), s("src/pkg/core.py", "helper")) in calls
    assert (s("tests/test_api.py", "test_handle"), s("src/pkg/api.py", "handle")) in calls


def test_labels_and_line_ranges(graph):
    test_fn = graph.nodes[symbol_node_id(REPO, "tests/test_api.py", "test_handle")]
    assert test_fn.label == NodeLabel.TEST
    run = graph.nodes[symbol_node_id(REPO, "src/pkg/core.py", "Engine.run")]
    assert run.label == NodeLabel.METHOD and (run.properties["start_line"], run.properties["end_line"]) == (9, 11)


def test_every_edge_connects_existing_nodes(graph):
    assert all(s in graph.nodes and t in graph.nodes for (s, t, _) in graph.edges)


def test_git_history_becomes_commit_nodes_and_bulk_commits_are_skipped(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t"), git("config", "user.name", "t")
    for i, names in enumerate([["a.py"], ["a.py", "b.py"], ["a.py", "b.py", "c.py"]]):
        for n in names:
            (tmp_path / n).write_text(f"x = {i}\n")
        git("add", "-A")
        git("commit", "-q", "-m", f"change {i}")
    head = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    files = [(n, (tmp_path / n).read_text()) for n in ("a.py", "b.py", "c.py")]
    g = RepositoryGraphExtractor("o/r", head).extract(files, repo_dir=tmp_path, max_files_per_commit=2)
    commits = [n for n in g.nodes.values() if n.label == NodeLabel.COMMIT]
    assert len(commits) == 2 and g.history["bulk_commits_skipped"] == 1
    assert {n.properties["name"] for n in commits} == {"change 0", "change 1"}
    assert len(edges(g, R.MODIFIES)) == 3
