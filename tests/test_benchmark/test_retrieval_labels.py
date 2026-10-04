"""
Tests for the MEIB dev+val retrieval labels (WORK_PLAN B1, docs/RETRIEVAL_LABELS.md).

The structural tests run anywhere. The rebuild test needs both repositories
checked out at the pinned commits in .corpus_cache/ and Qdrant running; it is
skipped otherwise.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from benchmark import retrieval_labels as rl
from knowledge.schemas.benchmark import RequiredEvidence, RetrievalGroundTruth


@pytest.fixture(scope="module")
def label_set():
    return rl.load_labels()


@pytest.fixture(scope="module")
def split_ids():
    splits = json.loads(rl.SPLITS_PATH.read_text(encoding="utf-8"))["splits"]
    return {name: set(ids) for name, ids in splits.items()}


def _evidence(**kw):
    base = dict(file="src/a.py", start_line=1, end_line=2, why="x", span_sha256="sha256:0")
    return RequiredEvidence(**{**base, **kw})


def _label(**kw):
    base = dict(
        task_id="t", split="dev", repository="o/r", commit_sha="0" * 40,
        relevant_files=["src/a.py"], required_evidence=[_evidence()],
        label_status="draft", annotator="a",
    )
    return RetrievalGroundTruth(**{**base, **kw})


# --- Held-out protection ---------------------------------------------------------


def test_labels_cover_exactly_dev_and_val(label_set, split_ids):
    labelled = {l.task_id for l in label_set.labels}
    assert labelled == split_ids["dev"] | split_ids["val"]
    assert not labelled & split_ids["test"]


def test_split_recorded_correctly(label_set, split_ids):
    for l in label_set.labels:
        assert l.task_id in split_ids[l.split]


def test_loader_never_reads_test_tasks(split_ids):
    tasks, split_of = rl.load_dev_val_tasks()
    assert not set(tasks) & split_ids["test"]
    assert set(split_of.values()) == {"dev", "val"}


# --- Label content -----------------------------------------------------------------


def test_every_label_is_pinned_to_the_ingested_commit(label_set):
    assert label_set.repositories == rl.PINNED_COMMITS
    for l in label_set.labels:
        assert l.commit_sha == rl.PINNED_COMMITS[l.repository]


def test_every_evidence_span_is_in_the_index(label_set):
    for l in label_set.labels:
        for e in l.required_evidence:
            assert e.chunk_ids, f"{l.task_id}: {e.file}:{e.start_line} overlaps no indexed chunk"


def test_status_counts_and_no_unreviewed_verified(label_set):
    statuses = [l.label_status for l in label_set.labels]
    assert "verified" not in statuses  # only a named human reviewer may set this
    flagged = [l for l in label_set.labels if l.label_status == "flagged"]
    assert [l.task_id for l in flagged] == ["eih-phase1-ops-052"]


def test_expected_citations_match_evidence(label_set):
    for l in label_set.labels:
        assert l.expected_citations == [
            f"[{e.file}:L{e.start_line}-L{e.end_line}]" for e in l.required_evidence
        ]


# --- Schema validators -------------------------------------------------------------


def test_schema_rejects_test_split():
    with pytest.raises(ValidationError, match="blind protocol"):
        _label(split="test")


def test_schema_requires_notes_when_flagged():
    with pytest.raises(ValidationError, match="explain why"):
        _label(label_status="flagged", required_evidence=[], relevant_files=[])


def test_schema_requires_evidence_unless_flagged():
    with pytest.raises(ValidationError, match="at least one evidence span"):
        _label(required_evidence=[])


def test_schema_requires_reviewer_for_verified():
    with pytest.raises(ValidationError, match="verified_by"):
        _label(label_status="verified")


def test_schema_requires_evidence_files_in_relevant_files():
    with pytest.raises(ValidationError, match="relevant_files"):
        _label(relevant_files=["src/other.py"])


@pytest.mark.parametrize("path", ["/abs/a.py", "src\\a.py", "../a.py"])
def test_schema_rejects_non_relative_paths(path):
    with pytest.raises(ValidationError, match="repo-relative"):
        _evidence(file=path)


def test_schema_rejects_reversed_span():
    with pytest.raises(ValidationError, match="end_line"):
        _evidence(start_line=5, end_line=4)


# --- Rebuild (integration) ---------------------------------------------------------


def _sources_available() -> bool:
    for repo, sha in rl.PINNED_COMMITS.items():
        head = rl.repo_dir(repo) / ".git" / "HEAD"
        if not head.is_file() or head.read_text().strip() != sha:
            return False
    try:
        import urllib.request
        urllib.request.urlopen(f"{rl.QDRANT_URL}/readyz", timeout=2)
    except Exception:
        return False
    return True


@pytest.mark.integration
@pytest.mark.skipif(not _sources_available(), reason="pinned repos in .corpus_cache and Qdrant required")
def test_rebuild_matches_committed_labels():
    assert rl.render(rl.build()) == rl.LABELS_PATH.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.skipif(not _sources_available(), reason="pinned repos in .corpus_cache required")
def test_span_hashes_match_pinned_source(label_set):
    for l in label_set.labels:
        for e in l.required_evidence:
            assert rl._span_sha(l.repository, e.file, e.start_line, e.end_line) == e.span_sha256
