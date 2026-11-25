"""Tests for the benchmark review queue (benchmark/review.py, scripts/review.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from benchmark.review import (
    CHECKS, Decision, EvidenceSnippet, ReviewBatch, ReviewError, ReviewItem, ReviewStore,
    calibration_agreement, cohen_kappa, fleiss_kappa, progress_report,
)

T0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


def _item(item_id="t1", split="dev", drafted_by="claude-opus-5.5", requested_by="Avaneesh Kumar Verma", **kw):
    base = dict(item_id=item_id, kind="new_task", split=split, repository="pallets/flask", commit_sha="c" * 40,
                sdlc_stage="testing", task_type="test_generation", query="Q?", proposed_answer="A.",
                evidence=[EvidenceSnippet(file="src/a.py", start_line=1, end_line=2, text="x\ny",
                                          span_sha256="sha256:0")],
                drafted_by=drafted_by, requested_by=requested_by)
    return ReviewItem(**{**base, **kw})


@pytest.fixture
def store(tmp_path):
    (tmp_path / "reviewers.yaml").write_text(
        "reviewers:\n  - Avaneesh Kumar Verma\n  - Sanvi\n  - Aayan\n  - Radhesh\n", encoding="utf-8")
    return ReviewStore(tmp_path)


def _batch(store, items, batch_id="b1", purpose="review", assigned=()):
    b = ReviewBatch(batch_id=batch_id, created_at=T0.isoformat(), purpose=purpose, assigned_to=list(assigned),
                    items=items)
    store.save_batch(b)
    return b


# --- decision rules ------------------------------------------------------------------


def test_approve_needs_all_checks_and_fix_needs_note_and_failed_check():
    ok = dict(item_id="t", batch_id="b", item_sha="s", reviewer="Sanvi", minutes_spent=3, decided_at="x")
    Decision(decision="approve", checks={c: True for c in CHECKS}, **ok)
    with pytest.raises(ValidationError, match="all four checks"):
        Decision(decision="approve", checks={**{c: True for c in CHECKS}, "answer_correct": False}, **ok)
    with pytest.raises(ValidationError, match="needs a note"):
        Decision(decision="fix", checks={**{c: True for c in CHECKS}, "answer_correct": False}, **ok)
    with pytest.raises(ValidationError, match="failed check"):
        Decision(decision="reject", checks={c: True for c in CHECKS}, note="bad", **ok)


def test_no_self_approval_for_drafter_or_requester(store):
    _batch(store, [_item()])
    with pytest.raises(ReviewError, match="no self-approval"):
        store.decide("t1", "Avaneesh", "approve", minutes=2, now=T0)  # requested it
    _batch(store, [_item("t2", drafted_by="Sanvi", requested_by=None)], batch_id="b2")
    with pytest.raises(ReviewError, match="no self-approval"):
        store.decide("t2", "sanvi", "approve", minutes=2, now=T0)  # drafted it
    assert store.next_item("Avaneesh") is not None and store.next_item("Avaneesh")[1].item_id == "t2"


def test_unknown_reviewer_refused(store):
    _batch(store, [_item()])
    with pytest.raises(ReviewError, match="not exactly one reviewer"):
        store.decide("t1", "Mallory", "approve", minutes=2, now=T0)


def test_held_out_items_need_two_different_reviewers(store):
    _batch(store, [_item(split="test")])
    store.decide("t1", "Sanvi", "approve", minutes=4, now=T0)
    _, item = store.find("t1")
    assert store.status(item) == "partially_approved"
    store.decide("t1", "Sanvi", "approve", minutes=1, now=T0)  # same person again does not count twice
    assert store.status(item) == "partially_approved"
    store.decide("t1", "Aayan", "approve", minutes=5, now=T0)
    assert store.status(item) == "approved"


def test_dev_item_needs_one_review_and_reject_wins(store):
    _batch(store, [_item(), _item("t2")])
    store.decide("t1", "Sanvi", "approve", minutes=3, now=T0)
    store.decide("t2", "Aayan", "reject", failed=["answer_correct"], note="wrong line", minutes=3, now=T0)
    assert store.status(store.find("t1")[1]) == "approved"
    assert store.status(store.find("t2")[1]) == "rejected"


def test_editing_an_item_voids_old_decisions(store):
    b = _batch(store, [_item()])
    store.decide("t1", "Sanvi", "approve", minutes=3, now=T0)
    b.items[0] = b.items[0].model_copy(update={"proposed_answer": "A different answer."})
    store.save_batch(b, overwrite=True)
    assert store.status(store.find("t1")[1]) == "pending"


def test_assignment_enforced(store):
    _batch(store, [_item()], assigned=["Aayan"])
    with pytest.raises(ReviewError, match="assigned"):
        store.decide("t1", "Sanvi", "approve", minutes=2, now=T0)
    assert store.next_item("Sanvi") is None


def test_item_queued_once_and_batch_size_limit(store):
    _batch(store, [_item()])
    with pytest.raises(ReviewError, match="already queued"):
        _batch(store, [_item()], batch_id="b2")
    with pytest.raises(ValidationError):
        ReviewBatch(batch_id="x", created_at="t", purpose="review", items=[_item(f"i{n}") for n in range(26)])


def test_timer_records_minutes(store):
    _batch(store, [_item()])
    store.start("Radhesh", "t1", now=T0)
    rec = store.decide("t1", "Radhesh", "approve", now=T0 + timedelta(minutes=7, seconds=30))
    assert rec.minutes_spent == 7.5
    with pytest.raises(ReviewError, match="no timer"):
        store.decide("t1", "Aayan", "approve", now=T0)


# --- agreement -------------------------------------------------------------------------


def test_cohen_kappa_matches_sklearn():
    from sklearn.metrics import cohen_kappa_score

    a = ["approve", "approve", "fix", "reject", "approve", "fix", "approve", "reject", "approve", "approve"]
    b = ["approve", "fix", "fix", "reject", "approve", "approve", "approve", "reject", "fix", "approve"]
    assert cohen_kappa(a, b) == pytest.approx(cohen_kappa_score(a, b))
    assert cohen_kappa(["approve"] * 3, ["approve"] * 3) is None


def test_fleiss_kappa_known_value():
    # Fleiss (1971)-style check: perfect agreement -> 1; computed example vs hand calculation.
    assert fleiss_kappa([["a", "a", "a"], ["b", "b", "b"]]) == pytest.approx(1.0)
    r = [["a", "a", "b"], ["a", "b", "b"], ["a", "a", "a"], ["b", "b", "b"]]
    # P_i = [1/3, 1/3, 1, 1] -> P_bar = 2/3 ; p_a = p_b = 0.5 -> Pe = 0.5 ; kappa = (2/3-0.5)/0.5
    assert fleiss_kappa(r) == pytest.approx(1 / 3)


def test_calibration_agreement_over_all_four(store):
    items = [_item(f"c{n}", requested_by=None) for n in range(3)]
    _batch(store, items, batch_id="cal", purpose="calibration", assigned=store.reviewers())
    for rev in store.reviewers():
        for n in range(3):
            if rev == "Radhesh" and n == 2:
                store.decide(f"c{n}", rev, "fix", failed=["labels_fit"], note="stage", minutes=2, now=T0)
            else:
                store.decide(f"c{n}", rev, "approve", minutes=2, now=T0)
    # calibration items stay visible until every assigned reviewer has decided
    assert store.next_item("Sanvi") is None
    out = calibration_agreement(store, "cal")
    assert out["items_rated_by_all"] == 3 and len(out["pairwise_cohen_kappa"]) == 6
    assert out["fleiss_kappa"] is not None


# --- report ------------------------------------------------------------------------------


def test_progress_report_counts_and_reject_alert(store, tmp_path):
    _batch(store, [_item(f"r{n}", requested_by=None) for n in range(4)])
    store.decide("r0", "Sanvi", "approve", minutes=5, now=T0)
    store.decide("r1", "Sanvi", "reject", failed=["question_clear"], note="vague", minutes=5, now=T0)
    store.decide("r2", "Aayan", "approve", minutes=4, now=T0)
    ask = tmp_path / "ASK_ME.md"
    ask.write_text("- [ ] D4 baseline\n- [x] done\n", encoding="utf-8")
    rep = progress_report(store, "2026-10-06", [], ask)
    assert rep["approved_total"] == 2 and rep["approved_per_stage"] == {"testing": 2}
    assert rep["reject_rate"] == 0.333 and rep["reject_alert"] is True
    assert rep["open_blockers"] == ["D4 baseline"]
    assert rep["minutes_per_reviewer"] == {"Aayan": 4.0, "Sanvi": 10.0}


def test_cli_refuses_test_tasks_outside_correctness_pass(tmp_path, monkeypatch):
    import json

    from benchmark import retrieval_labels as rl
    from scripts import review as cli

    (tmp_path / "reviewers.yaml").write_text("reviewers:\n  - Sanvi\n", encoding="utf-8")
    test_id = json.loads(rl.SPLITS_PATH.read_text(encoding="utf-8"))["splits"]["test"][0]
    rc = cli.main(["--root", str(tmp_path), "import-existing", "--batch", "x", "--ids", test_id,
                   "--drafted-by", "unknown"])
    assert rc == 2 and not (tmp_path / "queue").exists()


def test_correctness_pass_queues_tasks_whose_evidence_cannot_be_shown(monkeypatch):
    import benchmark.review as rv
    import experiments.m5.manifest as mf

    def broken(*a, **k):
        raise ReviewError("pallets/flask:x.py has 10 lines; evidence ends at 99")

    monkeypatch.setattr(rv, "snippet", broken)
    monkeypatch.setattr(mf, "wave1_repository_pins", lambda: {"pallets/flask": "c" * 40})
    task = {"task_id": "t9", "repository": "pallets/flask", "sdlc_stage": "testing", "task_type": "test_generation",
            "query": "Q", "ground_truth": "A",
            "source_evidence": [{"file_path": "x.py", "line_start": 90, "line_end": 99}]}
    with pytest.raises(ReviewError):
        rv.item_from_task(task, "test", "lead_researcher")
    item = rv.item_from_task(task, "test", "lead_researcher", allow_evidence_defects=True)
    assert item.evidence == [] and item.status_note.startswith("EVIDENCE DEFECT")
    assert item.required_reviews == 2
