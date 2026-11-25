"""OKF producer (deterministic, owner-aware) and Qdrant/Neo4j sync (isolated from research data)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from knowledge.okf.bundle import OKFBundle
from knowledge.okf.collaboration import KnowledgeWorkspace
from knowledge.okf.document import OKFDocument
from knowledge.okf.producer import ACTOR, produce_repository, write_produced
from knowledge.okf.sync import MAX_TOKENS, _sections, concept_chunks


def _git_repo(root: Path) -> str:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text('"""The package."""\n', encoding="utf-8")
    (root / "pkg" / "index.py").write_text("def build():\n    return 1\n", encoding="utf-8")  # reserved stem
    (root / "pkg" / "core.py").write_text(
        '"""Core logic.\n\nMore."""\nfrom pkg import index\n\nclass Engine(Base):\n    """Runs things."""\n'
        "    def run(self):\n        pass\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (root / "pkg" / "broken.py").write_text("def (:\n", encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


@pytest.fixture
def produced(tmp_path: Path):
    sha = _git_repo(tmp_path / "repo")
    entry = {"repo_id": "demo", "owner": "acme", "name": "demo", "language": "Python", "selected_tag": "v1",
             "selected_commit": sha, "wave": 1}
    return sha, produce_repository(entry, tmp_path / "repo", "2026-11-22T00:00:00Z")


def test_producer_extracts_modules_skips_tests_and_unparseable(produced):
    sha, concepts = produced
    ids = {c.concept_id for c in concepts}
    assert ids == {"code/demo/pkg/__init__.py", "code/demo/pkg/index.py", "code/demo/pkg/core.py",
                   "repositories/demo"}
    core = next(c for c in concepts if c.concept_id.endswith("core.py"))
    assert core.frontmatter["description"] == "Core logic."
    assert core.frontmatter["resource"] == f"https://github.com/acme/demo/blob/{sha}/pkg/core.py"
    assert core.frontmatter["generated"]["by"] == ACTOR and "verified" not in core.frontmatter
    assert "`Engine`" in core.body and "[pkg.index](/code/demo/pkg/index.py.md)" in core.body


def test_producer_refuses_unpinned_checkout(tmp_path: Path):
    _git_repo(tmp_path / "repo")
    with pytest.raises(RuntimeError):
        produce_repository({"repo_id": "d", "owner": "a", "name": "d", "selected_commit": "0" * 40},
                           tmp_path / "repo", "2026-11-22T00:00:00Z")


def test_produced_bundle_is_conformant_and_rerun_is_idempotent(produced, tmp_path: Path):
    _, concepts = produced
    (tmp_path / "b").mkdir()
    bundle = OKFBundle(tmp_path / "b")
    first = write_produced(bundle, concepts)
    assert len(first.written) == 4 and not first.errors
    bundle.regenerate_indexes()
    bundle.reload()
    rep = bundle.conformance()
    assert rep.conformant and not rep.broken_links
    second = write_produced(bundle, concepts)
    assert not second.written and len(second.unchanged) == 4


def test_producer_never_overwrites_human_or_approved_knowledge(produced, tmp_path: Path):
    _, concepts = produced
    (tmp_path / "b").mkdir()
    bundle = OKFBundle(tmp_path / "b")
    write_produced(bundle, concepts)
    ws = KnowledgeWorkspace(bundle, tmp_path / "state")
    cur = bundle.get("code/demo/pkg/core.py")
    ws.human_edit(cur.id, dict(cur.doc.frontmatter), "Hand-written explanation.\n", "human:a", cur.doc.content_hash())
    rep = write_produced(bundle, concepts)
    assert rep.skipped_not_owned == ["code/demo/pkg/core.py"]
    assert bundle.get("code/demo/pkg/core.py").doc.body == "Hand-written explanation.\n"


def test_chunks_fit_embedding_window_and_have_stable_ids():
    words = lambda t: len(t.split()) + 2  # noqa: E731 - stand-in token counter
    body = "# A\n\n" + ("word " * 2000) + "\n\n# B\n\nshort\n```\n# not a heading\n```\n"
    doc = OKFDocument(frontmatter={"type": "Note", "title": "T"}, body=body)
    from knowledge.okf.bundle import Concept
    c = Concept("notes/t", Path("notes/t.md"), doc)
    chunks = concept_chunks("b", c, count=words)
    assert all(words(ch.text) <= MAX_TOKENS for ch in chunks) and len(chunks) > 2
    assert [ch.point_id for ch in chunks] == [ch.point_id for ch in concept_chunks("b", c, count=words)]
    assert [h for h, _ in _sections(body)] == ["A", "B"]


# ---------------------------------------------------------------- live services


def _services():
    try:
        from core.config import settings
        from knowledge.graph.neo4j import Neo4jGraphStore
        from knowledge.vector.qdrant import QdrantVectorStore
        vs = QdrantVectorStore()
        vs.connect()
        g = Neo4jGraphStore()
        return (vs, g) if g.is_available() and vs.collection_exists(settings.vector_store.collection_name) else None
    except Exception:  # noqa: BLE001
        return None


@pytest.mark.integration
def test_live_sync_is_incremental_and_leaves_research_counts_untouched(tmp_path: Path):
    svc = _services()
    if svc is None:
        pytest.skip("Qdrant with the research collection and Neo4j are required")
    from core.config import settings
    from knowledge.okf.sync import OKFGraphProjection, OKFVectorIndex
    vs, graph = svc
    research = settings.vector_store.collection_name
    before = (vs.count(research), graph.count_nodes(), graph.count_edges())

    name = f"pytest-{uuid.uuid4().hex[:8]}"
    coll = "eih_okf_pytest"
    root = tmp_path / name
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.md").write_text("---\ntype: Note\ntitle: X\n---\n\nSee [y](/a/y.md).\n", encoding="utf-8")
    (root / "a" / "y.md").write_text("---\ntype: Note\ntitle: Y\n---\n\nTarget.\n", encoding="utf-8")
    bundle = OKFBundle(root)
    vec, proj = OKFVectorIndex(collection=coll), OKFGraphProjection(graph)
    try:
        assert vec.sync_bundle(bundle, name)["points"] == 2
        assert proj.sync_bundle(bundle, name) == {"concepts": 2, "edges": 1, "describes": 0}

        ws = KnowledgeWorkspace(bundle, tmp_path / "state", name=name)
        ws.on_change(lambda n, ids: (vec.sync_concepts(bundle, n, ids), proj.sync_concepts(bundle, n, ids)))
        ws.human_edit("a/z", {"type": "Note", "title": "Zed"}, "Links [x](/a/x.md).\n", "human:t", None)
        assert vec.count(name) == 3
        assert proj.count(name) == {"concepts": 3, "links": 2, "describes": 0}
        hits = vec.search("Zed", bundle=name, limit=1)
        assert hits and hits[0]["concept_id"] == "a/z"
        assert (vs.count(research), graph.count_nodes(), graph.count_edges()) == before
    finally:
        graph.query("MATCH (c:OKFConcept {bundle: $b}) DETACH DELETE c", {"b": name})
        vec.client.delete_collection(coll)
    assert (vs.count(research), graph.count_nodes(), graph.count_edges()) == before
