"""scripts/recover_rating_key.py on synthetic data only (never the real trials or key)."""

from __future__ import annotations

import pytest

from benchmark.rating import RatingBatch, build_batch
from scripts import recover_rating_key as rk

STAGES = ("requirements", "architecture", "development", "testing", "code_review", "maintenance")
SYSTEMS = ("baseline_a", "baseline_b", "system_c", "system_d", "system_e", "system_e_routed")


def _split(name):
    out = []
    for st in STAGES:
        for sy in SYSTEMS:
            for k in range(2):
                for trial in (0, 1):
                    out.append({"task_id": f"{name}-{st}-{k}", "system_id": sy, "trial_index": trial,
                                "metadata": {"sdlc_stage": st}, "is_grounded_refusal": sy == "system_e" and k == 1,
                                "generated_answer": f"{name} answer {st} {sy} {k} trial {trial}"})
    return out


@pytest.fixture
def built(tmp_path):
    dev, val = _split("dev"), _split("val")
    queries = {t["task_id"]: f"question about {t['task_id']}" for t in dev + val}
    tasks = {tid: {"query": q, "ground_truth": "gt"} for tid, q in queries.items()}
    # built from val + dev, like the order method A has to rediscover
    batch = build_batch(val + dev, tasks, {}, "m1-syn", n=40, key_dir=tmp_path / "keys", out_dir=tmp_path / "rating",
                        exclude_tasks=["dev-testing-0"])
    original = (tmp_path / "keys" / "m1-syn_key.json").read_bytes()
    (tmp_path / "keys" / "m1-syn_key.json").unlink()                  # the key is lost
    return tmp_path, batch, [dev, val], queries, original


def test_recovery_reproduces_the_checksum(built):
    tmp, batch, trials, queries, original = built
    out = tmp / "recovered" / "m1-syn_key.json"
    rep = rk.recover(batch, trials, queries, out)
    assert rep["result"] == "MATCH" and rep["agree"] and rep["method_b"]["exactly_one"] == 40
    assert out.read_bytes() == original and rk.checksum(out.read_bytes()) == batch.key_sha256
    with pytest.raises(FileExistsError):                              # never overwritten
        rk.recover(batch, trials, queries, out)


def test_tampered_answer_is_reported_and_nothing_written(built):
    tmp, batch, trials, queries, _ = built
    data = batch.model_dump()
    data["units"][0]["answer"] += " (edited)"
    tampered = RatingBatch.model_validate(data)
    out = tmp / "recovered" / "m1-syn_key.json"
    rep = rk.recover(tampered, trials, queries, out)
    assert rep["result"] == "NO MATCH" and rep["method_b"]["none"] == 1 and rep["written"] is None
    assert not out.exists()


def test_wrong_checksum_is_not_forced(built):
    tmp, batch, trials, queries, _ = built
    bad = batch.model_copy(update={"key_sha256": "sha256:" + "0" * 64})
    out = tmp / "recovered" / "k.json"
    rep = rk.recover(bad, trials, queries, out)
    assert rep["result"] == "NO MATCH" and not rep["method_a_match"] and not out.exists()


def test_ambiguous_answers_block_the_recovery(built):
    """Two trials with the same answer to the same question: B cannot decide, so nothing is written."""
    tmp, batch, trials, queries, _ = built
    unit = batch.units[0]
    dev, val = trials
    twin = next(t for t in dev + val if t["generated_answer"] == unit.answer)
    clone = {**twin, "system_id": "zz_other_system"}
    rep = rk.recover(batch, [dev + [clone], val], queries, tmp / "k.json")
    assert rep["method_b"]["several"] == 1 and rep["result"] == "NO MATCH" and not (tmp / "k.json").exists()


def test_main_refuses_a_key_path_inside_the_repo():
    assert rk.main(["--batch", "m1-rating-01", "--out", str(rk.REPO_ROOT / "key.json")]) == 2
