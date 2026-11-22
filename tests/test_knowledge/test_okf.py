"""
OKF (Open Knowledge Format v0.2, reads v0.1) conformance and collaboration tests.

Spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
Section numbers in test names/comments refer to it. External bundles in
fixtures/okf_external/ are Google's own sample bundles (Apache-2.0, see NOTICE.md).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from knowledge.okf.bundle import OKFBundle, OKFPathError, validate_concept_id
from knowledge.okf.collaboration import (
    APPROVED,
    CONFLICT,
    REJECTED,
    CollaborationError,
    ConcurrentEditError,
    KnowledgeWorkspace,
)
from knowledge.okf.document import (
    TRUST_HUMAN,
    TRUST_MACHINE,
    TRUST_UNVERIFIED,
    OKFDocument,
    OKFParseError,
    is_valid_actor,
)

EXTERNAL = Path(__file__).parent / "fixtures" / "okf_external"
AGENT = "eih_agent/qwen2.5-coder-7b"
HUMAN = "human:avaneesh"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def bundle(tmp_path: Path) -> OKFBundle:
    root = tmp_path / "b"
    write(root, "apis/auth.md", "---\ntype: API Endpoint\ntitle: Auth\ndescription: Login.\ntags: [security]\n---\n\n"
          "# Notes\n\nUses the [session store](/components/session.md) and [docs](https://example.com).\n"
          "See [missing](/components/not-yet.md).\n")
    write(root, "components/session.md", "---\ntype: Component\ntitle: Session store\n---\n\n"
          "Backs [auth](../apis/auth.md).\n```\n[not a link](/apis/auth.md)\n```\n")
    return OKFBundle(root)


# ---------------------------------------------------------------- §4 documents


def test_minimal_concept_with_only_type_is_conformant():  # §4.1, §11
    doc = OKFDocument.parse("---\ntype: Metric\n---\n\nBody\n")
    assert doc.validate() == [] and doc.type == "Metric"


@pytest.mark.parametrize("text", ["---\ntitle: X\n---\nbody\n", "---\ntype: ''\n---\n", "no frontmatter\n"])
def test_missing_type_or_frontmatter_is_an_error(text):  # §11.1-2
    assert OKFDocument.parse(text).validate()


def test_unterminated_or_non_mapping_frontmatter_raises():
    with pytest.raises(OKFParseError):
        OKFDocument.parse("---\ntype: X\nbody without closing\n")
    with pytest.raises(OKFParseError):
        OKFDocument.parse("---\n- a\n- b\n---\n")


def test_unknown_keys_and_timestamps_round_trip_unchanged():  # §4.1 extensions, §5
    text = ("---\ntype: Weird Custom Type\nx_custom: {a: 1}\ngenerated: {by: tool/1, at: 2026-06-30T14:00:00Z}\n"
            "stale_after: 2026-09-23T00:00:00Z\n---\n\n# Body\n")
    doc = OKFDocument.parse(text)
    assert doc.frontmatter["x_custom"] == {"a": 1}
    assert doc.frontmatter["stale_after"] == "2026-09-23T00:00:00Z"  # kept as written, not a datetime
    again = OKFDocument.parse(doc.serialize())
    assert again.frontmatter == doc.frontmatter and again.body == doc.body
    assert again.serialize() == doc.serialize()


def test_trust_tiers_and_bare_verified_mapping():  # §5.2, §5.3
    assert OKFDocument(frontmatter={"type": "T"}).trust_tier == TRUST_UNVERIFIED
    assert OKFDocument(frontmatter={"type": "T", "verified": {"by": "process:nightly", "at": "x"}}).trust_tier == TRUST_MACHINE
    fm = {"type": "T", "verified": [{"by": "process:n", "at": "x"}, {"by": "human:a", "at": "y"}]}
    assert OKFDocument(frontmatter=fm).trust_tier == TRUST_HUMAN


def test_staleness_and_lifecycle_defaults():  # §5.4, §5.5
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    assert OKFDocument(frontmatter={"type": "T", "stale_after": "2026-06-15T00:00:00Z"}).is_stale(now)
    assert not OKFDocument(frontmatter={"type": "T", "stale_after": "2027-01-01T00:00:00Z"}).is_stale(now)
    assert not OKFDocument(frontmatter={"type": "T", "stale_after": "2026-01-01"}).is_stale(now)  # no offset: ignored
    assert OKFDocument(frontmatter={"type": "T"}).status == "stable"


def test_v01_timestamp_fallback():  # §13.1
    doc = OKFDocument.parse("---\ntype: Metric\ntimestamp: '2026-05-28T22:53:05+00:00'\n---\n")
    assert doc.generated_at == "2026-05-28T22:53:05+00:00"
    assert any("v0.1" in w for w in doc.warnings())


def test_actor_convention():  # §7
    assert is_valid_actor("human:jsmith@acme") and is_valid_actor("process:nightly")
    assert is_valid_actor("reference_agent/gemini-2.5-pro") and not is_valid_actor("just a name")


# ---------------------------------------------------------------- §3, §6 bundles and links


def test_discovery_skips_reserved_files(bundle: OKFBundle):  # §3.1
    write(bundle.root, "index.md", "# Index\n")
    write(bundle.root, "log.md", "# Log\n\n## 2026-11-22\n* x\n")
    bundle.reload()
    assert set(bundle.concepts) == {"apis/auth", "components/session"}
    assert len(bundle.index_files) == 1 and len(bundle.log_files) == 1


def test_absolute_and_relative_links_resolve(bundle: OKFBundle):  # §6.1
    edges = bundle.concept_edges()
    assert ("apis/auth", "components/session") in edges
    assert ("components/session", "apis/auth") in edges
    assert len(edges) == 2  # link inside a code fence is not a link; external link is not an edge


def test_broken_links_are_reported_not_rejected(bundle: OKFBundle):  # §6.1, §11
    rep = bundle.conformance()
    assert rep.conformant
    assert [l.target_raw for l in rep.broken_links] == ["/components/not-yet.md"]


def test_link_escaping_bundle_is_broken(bundle: OKFBundle):
    resolved, external = bundle.resolve_link("apis/auth", "../../../etc/passwd.md")
    assert resolved is None and not external


def test_non_conformant_files_reported_not_dropped(tmp_path: Path):  # §11
    write(tmp_path, "ok.md", "---\ntype: T\n---\n")
    write(tmp_path, "notype.md", "---\ntitle: X\n---\n")
    write(tmp_path, "broken.md", "---\ntype: [unclosed\n---\n")
    write(tmp_path, "sub/index.md", "---\nokf_version: '0.2'\n---\n# X\n")  # frontmatter only allowed at root
    write(tmp_path, "log.md", "# Log\n\n## yesterday\n* x\n")
    rep = OKFBundle(tmp_path).conformance()
    paths = {e.path for e in rep.errors}
    assert not rep.conformant
    assert {"notype.md", "broken.md", "sub/index.md", "log.md"} <= paths
    assert "ok.md" not in paths


def test_concept_id_validation():
    assert validate_concept_id("/tables/orders.md") == "tables/orders"
    for bad in ["../x", "a/../../b", "", "dir/index", "log"]:
        with pytest.raises(OKFPathError):
            validate_concept_id(bad)


def test_search_neighbours_types_tags(bundle: OKFBundle):
    hits = bundle.search("session")
    assert hits[0][0].id == "components/session"
    assert bundle.neighbours("apis/auth") == ["components/session"]
    assert bundle.types() == {"API Endpoint": 1, "Component": 1}
    assert bundle.tags() == {"security": 1}


def test_index_regeneration_is_conformant_and_declares_version(bundle: OKFBundle):  # §8, §12
    written = bundle.regenerate_indexes()
    assert {p.relative_to(bundle.root).as_posix() for p in written} == {"index.md", "apis/index.md", "components/index.md"}
    root_idx = (bundle.root / "index.md").read_text(encoding="utf-8")
    assert root_idx.startswith('---\nokf_version: "0.2"\n---')
    assert "* [Auth](auth.md) - Login." in (bundle.root / "apis/index.md").read_text(encoding="utf-8")
    bundle.reload()
    assert bundle.conformance().conformant and bundle.declared_version == "0.2"


def test_log_entries_newest_first(bundle: OKFBundle):  # §9
    from datetime import date
    bundle.append_log(["**Creation**: first"], day=date(2026, 11, 20))
    bundle.append_log(["**Update**: second"], day=date(2026, 11, 22))
    bundle.append_log(["**Update**: third"], day=date(2026, 11, 22))
    lines = (bundle.root / "log.md").read_text(encoding="utf-8").splitlines()
    assert lines.index("## 2026-11-22") < lines.index("## 2026-11-20")
    bundle.reload()
    assert bundle.conformance().conformant


# ---------------------------------------------------------------- external interoperability


@pytest.mark.parametrize("name,concepts", [("acme_retail", 9), ("crypto_bitcoin", 9)])
def test_external_google_bundles_are_consumed(tmp_path: Path, name: str, concepts: int):
    root = tmp_path / name
    shutil.copytree(EXTERNAL / name, root)
    b = OKFBundle(root)
    rep = b.conformance()
    assert rep.conformant, rep.errors
    assert rep.concepts == concepts and not rep.broken_links
    assert b.concept_edges()
    for c in b.concepts.values():  # round trip is a fixed point for every external concept
        once = OKFDocument.parse(c.doc.serialize())
        assert once.frontmatter == c.doc.frontmatter
        assert OKFDocument.parse(once.serialize()).serialize() == once.serialize()


def test_external_bundle_trust_and_computation_fields():
    b = OKFBundle(EXTERNAL / "acme_retail")
    assert b.get("metrics/revenue").doc.trust_tier == TRUST_HUMAN
    comp = [c for c in b.concepts.values() if c.doc.type == "Attested Computation"]
    assert comp and all(c.doc.frontmatter.get("runtime") for c in comp)


def test_eih_written_bundle_is_readable_by_reference_style_parser(bundle: OKFBundle, tmp_path: Path):
    """Portability: what EIH writes parses with a plain YAML + split reader (no EIH code)."""
    import yaml

    ws = KnowledgeWorkspace(bundle, tmp_path / "state")
    ws.human_edit("guides/deploy", {"type": "Playbook", "title": "Deploy"}, "# Steps\n\n1. Ship.\n", HUMAN, None)
    text = (bundle.root / "guides/deploy.md").read_text(encoding="utf-8")
    _, fm, body = text.split("---\n", 2)
    meta = yaml.safe_load(fm)
    assert meta["type"] == "Playbook" and meta["generated"]["by"] == HUMAN and "# Steps" in body


# ---------------------------------------------------------------- human-agent collaboration


@pytest.fixture
def ws(bundle: OKFBundle, tmp_path: Path) -> KnowledgeWorkspace:
    return KnowledgeWorkspace(bundle, tmp_path / "state")


def test_agent_cannot_approve_and_human_cannot_propose(ws: KnowledgeWorkspace):
    with pytest.raises(CollaborationError):
        ws.propose(kind="create", concept_id="x/y", frontmatter={"type": "T"}, body="", rationale="r", actor=HUMAN)
    p = ws.propose(kind="create", concept_id="x/y", frontmatter={"type": "T"}, body="b", rationale="r", actor=AGENT)
    with pytest.raises(CollaborationError):
        ws.approve(p.id, reviewer=AGENT)


def test_proposal_does_not_touch_bundle_until_approved(ws: KnowledgeWorkspace):
    p = ws.propose(kind="create", concept_id="components/cache", frontmatter={"type": "Component", "title": "Cache"},
                   body="LRU cache.\n", rationale="Asked about caching; no concept exists.", actor=AGENT,
                   evidence=[{"chunk": "flask/app.py:10-20"}])
    assert ws.bundle.get("components/cache") is None and not (ws.bundle.root / "components/cache.md").exists()
    synced = []
    ws.on_change(lambda name, ids: synced.append(ids))
    res = ws.approve(p.id, reviewer=HUMAN)
    assert res["status"] == APPROVED and synced == [["components/cache"]]
    doc = OKFBundle(ws.bundle.root).get("components/cache").doc
    assert doc.generated_by == AGENT and doc.trust_tier == TRUST_HUMAN
    assert "approved by `human:avaneesh`" in (ws.bundle.root / "log.md").read_text(encoding="utf-8")
    assert [r["action"] for r in ws.audit_trail()] == ["approve", "propose"]


def test_proposed_trust_fields_are_ignored(ws: KnowledgeWorkspace):
    p = ws.propose(kind="create", concept_id="a/b", rationale="r", actor=AGENT, body="",
                   frontmatter={"type": "T", "verified": {"by": "human:forged", "at": "x"}})
    assert "verified" not in p.proposed_frontmatter


def test_reviewer_edit_makes_reviewer_the_author(ws: KnowledgeWorkspace):
    cur = ws.bundle.get("apis/auth")
    p = ws.propose(kind="update", concept_id="apis/auth", frontmatter=dict(cur.doc.frontmatter, description="Wrong."),
                   body=cur.doc.body, rationale="r", actor=AGENT)
    ws.approve(p.id, reviewer=HUMAN, edited_frontmatter=dict(cur.doc.frontmatter, description="Corrected."))
    doc = ws.bundle.get("apis/auth").doc
    assert doc.description == "Corrected." and doc.generated_by == HUMAN


def test_stale_proposal_becomes_conflict_and_never_overwrites(ws: KnowledgeWorkspace):
    cur = ws.bundle.get("apis/auth")
    p = ws.propose(kind="update", concept_id="apis/auth", frontmatter=dict(cur.doc.frontmatter),
                   body="Agent rewrite.\n", rationale="r", actor=AGENT)
    ws.human_edit("apis/auth", dict(cur.doc.frontmatter), "Human fix.\n", HUMAN, base_hash=cur.doc.content_hash())
    res = ws.approve(p.id, reviewer=HUMAN)
    assert res["status"] == CONFLICT
    assert ws.bundle.get("apis/auth").doc.body == "Human fix.\n"


def test_human_edit_optimistic_concurrency(ws: KnowledgeWorkspace):
    with pytest.raises(ConcurrentEditError):
        ws.human_edit("apis/auth", {"type": "API Endpoint"}, "x", HUMAN, base_hash="stale")


def test_reject_needs_reason_and_leaves_bundle(ws: KnowledgeWorkspace):
    p = ws.propose(kind="deprecate", concept_id="components/session", frontmatter=None, body=None,
                   rationale="Superseded.", actor=AGENT)
    with pytest.raises(CollaborationError):
        ws.reject(p.id, HUMAN, "")
    assert ws.reject(p.id, HUMAN, "Still in use.").status == REJECTED
    assert ws.bundle.get("components/session").doc.status == "stable"
    with pytest.raises(CollaborationError):
        ws.approve(p.id, HUMAN)


def test_deprecation_keeps_concept_and_marks_status(ws: KnowledgeWorkspace):  # §5.4
    p = ws.propose(kind="deprecate", concept_id="components/session", frontmatter=None, body=None,
                   rationale="Superseded.", actor=AGENT)
    ws.approve(p.id, HUMAN)
    assert ws.bundle.get("components/session").doc.status == "deprecated"


def test_sync_failure_is_recorded_not_hidden(ws: KnowledgeWorkspace):
    def boom(name, ids):
        raise RuntimeError("qdrant down")

    ws.on_change(boom)
    res = ws.human_edit("notes/a", {"type": "Note"}, "x\n", HUMAN, None)
    assert res["sync_failures"] and "qdrant down" in res["sync_failures"][0]["error"]
    # newest first: the edit was written, then the sync after it failed
    assert [r["action"] for r in ws.audit_trail()] == ["sync_failed", "human_edit"]
