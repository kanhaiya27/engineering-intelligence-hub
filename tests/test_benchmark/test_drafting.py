"""Tests for the EIH-SWE drafting tool (benchmark/drafting.py)."""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone

import pytest

import benchmark.drafting as dr
import benchmark.review as rv
from benchmark.review import EvidenceSnippet, ReviewError, ReviewItem, ReviewStore

T0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
SRC = "import os\n\n\ndef helper(value):\n    return os.path.join('a', value)\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake pinned checkout with one 5-line file."""
    root = tmp_path / "flask"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text(SRC, encoding="utf-8")
    monkeypatch.setattr(dr, "_repo_path", lambda repository: root)

    def fake_snippet(repository, file, start, end):
        lines = (root / file).read_text(encoding="utf-8").splitlines()
        if end > len(lines):
            raise ReviewError(f"{repository}:{file} has {len(lines)} lines; evidence ends at {end}")
        text = "\n".join(lines[start - 1:end])
        return EvidenceSnippet(file=file, start_line=start, end_line=end, text=text,
                               span_sha256="sha256:" + hashlib.sha256(text.encode()).hexdigest())

    monkeypatch.setattr(dr, "snippet", fake_snippet)
    import experiments.m5.manifest as mf
    monkeypatch.setattr(mf, "wave1_repository_pins", lambda: {"pallets/flask": "c" * 40})
    return root


def _draft(**kw):
    base = dict(span_id="span-1", repository="pallets/flask", sdlc_stage="development", task_type="code_explanation",
                complexity="low", criticality="low", query="What does helper() in src/mod.py return?",
                answer="helper joins 'a' and value with os.path.join and returns the path.",
                evidence=[{"file": "src/mod.py", "start_line": 4, "end_line": 5}], acceptable_alternatives=[])
    return dr.Draft(**{**base, **kw})


@pytest.fixture
def store(tmp_path):
    (tmp_path / "rev").mkdir()
    (tmp_path / "rev" / "reviewers.yaml").write_text(
        "reviewers:\n  - Avaneesh Kumar Verma\n  - Sanvi\n  - Aayan\n  - Radhesh\n", encoding="utf-8")
    return ReviewStore(tmp_path / "rev")


# --- validation: evidence is never shown as present when it is not -----------------------


def test_valid_draft_passes(repo):
    ev = dr.validate_draft(_draft())
    assert ev[0].text.startswith("def helper")


@pytest.mark.parametrize("evidence, reason", [
    ([{"file": "src/mod.py", "start_line": 4, "end_line": 99}], "evidence ends at 99"),
    ([{"file": "src/missing.py", "start_line": 1, "end_line": 2}], "does not exist"),
    ([{"file": "src/mod.py", "start_line": 5, "end_line": 4}], "not a valid range"),
    ([{"file": "src/mod.py", "start_line": 0, "end_line": 2}], "not a valid range"),
    ([], "no evidence"),
])
def test_bad_evidence_fails_the_draft(repo, evidence, reason):
    with pytest.raises(ReviewError, match=reason):
        dr.validate_draft(_draft(evidence=evidence))


def test_type_must_belong_to_stage_and_answer_must_touch_evidence(repo):
    with pytest.raises(ReviewError, match="does not belong"):
        dr.validate_draft(_draft(task_type="test_generation"))
    with pytest.raises(ReviewError, match="shares no identifier"):
        dr.validate_draft(_draft(answer="It does something entirely unrelated, see docs."))


def test_queue_reports_failures_rotates_requester_and_excludes_them(repo, store):
    good = [_draft(span_id=f"s{i}", query=f"What does helper() return in case {i}?") for i in range(30)]
    bad = _draft(span_id="bad", evidence=[{"file": "src/mod.py", "start_line": 1, "end_line": 80}])
    out = dr.queue_drafts(good + [bad], "draft-t", store=store)
    assert out["queued"] == 30 and out["failed"][0]["span_id"] == "bad"
    assert [b["items"] for b in out["batches"]] == [25, 5]
    assert [b["requested_by"] for b in out["batches"]] == ["Avaneesh Kumar Verma", "Sanvi"]
    assert "Avaneesh Kumar Verma" not in out["batches"][0]["assigned_to"]
    assert "Sanvi" not in out["batches"][1]["assigned_to"]
    item = store.batches()[0].items[0]
    assert item.drafted_by == dr.DRAFTER and item.split == "unassigned" and "not verified" in item.status_note
    again = dr.queue_drafts(good[:1], "draft-u", store=store)
    assert again["queued"] == 0 and again["failed"][0]["reason"] == "duplicate question"


# --- split assigned at approval (S1) ---------------------------------------------------------


def _item(i, stage="testing", repo_="pallets/flask"):
    return ReviewItem(item_id=f"t{i}", kind="new_task", split="unassigned", repository=repo_, commit_sha="c" * 40,
                      sdlc_stage=stage, task_type="test_generation", query="Q?", proposed_answer="A.",
                      evidence=[EvidenceSnippet(file="a.py", start_line=1, end_line=1, text="x", span_sha256="s")],
                      drafted_by=dr.DRAFTER, requested_by="Avaneesh Kumar Verma")


def test_stratified_40_20_40_and_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "LOCKS_DIR", tmp_path / "locks")
    path = tmp_path / "assign.json"
    got = [dr.assign_split(_item(i), path=path, now=T0)["split"] for i in range(10)]
    assert Counter(got) == {"dev": 4, "val": 2, "test": 4}
    assert got[:5] == got[5:] == dr._slot_order("pallets/flask|testing")
    assert dr.assign_split(_item(0), path=path)["split"] == got[0]  # assigned once, never re-drawn


def test_test_slot_needs_a_second_independent_reviewer(store, monkeypatch, tmp_path):
    monkeypatch.setattr(dr, "LOCKS_DIR", tmp_path / "locks")
    order = dr._slot_order("pallets/flask|testing")
    k = order.index("test")
    items = [_item(i) for i in range(k + 1)]
    store.save_batch(rv.ReviewBatch(batch_id="b", created_at="t", purpose="review", items=items))
    for it in items:
        store.decide(it.item_id, "Sanvi", "approve", minutes=3, now=T0)
    test_item = items[k]
    assert store.effective_split(test_item) == "test"
    assert store.status(test_item) == "partially_approved"
    store.decide(test_item.item_id, "Aayan", "approve", minutes=3, now=T0)
    assert store.status(test_item) == "approved"
    tasks = dr.approved_tasks(store)
    t = next(x for x in tasks if x["task_id"] == test_item.item_id)
    assert t["split"] == "test" and t["human_approved_by"] == "Aayan; Sanvi" and t["fingerprint"].startswith("sha256:")


# --- lock (3e) ---------------------------------------------------------------------------------


def test_lock_dry_run_commit_and_post_lock_set(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "LOCKS_DIR", tmp_path / "locks")
    approved = [{"split": "test", "fingerprint": "sha256:a"}, {"split": "dev", "fingerprint": "sha256:b"}]
    dry = dr.lock_sets(approved, "2026-10-12")
    assert not (tmp_path / "locks").exists() and dry["sets"]["test"]["tasks"] == 1
    dr.lock_sets(approved, "2026-10-12", dry_run=False)
    with pytest.raises(ReviewError, match="never rewritten"):
        dr.lock_sets(approved, "2026-10-12", dry_run=False)
    rec = dr.assign_split(_item(99), path=tmp_path / "a.json", now=T0)
    assert rec["set"] == "eih-swe-post-lock-2026-10-12"


def test_fingerprint_matches_spec_fields():
    a = dr.task_fingerprint("q", "o/r", "c", "a")
    assert a == dr.task_fingerprint("q", "o/r", "c", "a") and a != dr.task_fingerprint("q", "o/r", "c", "b")
