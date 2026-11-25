"""Blind rating store (benchmark/rating.py) and the M1 selection rule (experiments/m1_selection.py).
All data here is synthetic test data, never results."""

from __future__ import annotations

import json

import pytest

from benchmark.rating import PAIRS, RatingStore, build_batch
from benchmark.review import ReviewError


def _trials():
    stages = ("requirements", "architecture", "development", "testing", "code_review", "maintenance")
    systems = ("baseline_a", "baseline_b", "system_c", "system_d", "system_e", "system_e_routed")
    out = []
    for st in stages:
        for sy in systems:
            for k in range(2):
                out.append({"task_id": f"{st}-{k}", "system_id": sy, "trial_index": 0, "metadata": {"sdlc_stage": st},
                            "generated_answer": f"answer {st} {systems.index(sy)} {k}", "is_grounded_refusal": sy == "system_e" and k})
    return out


@pytest.fixture
def setup(tmp_path):
    rev = tmp_path / "rev"
    rev.mkdir()
    (rev / "reviewers.yaml").write_text("reviewers:\n  - Avaneesh Kumar Verma\n  - Sanvi\n  - Aayan\n  - Radhesh\n",
                                        encoding="utf-8")
    tasks = {f"{st}-{k}": {"query": "q", "ground_truth": "gt"} for st in
             ("requirements", "architecture", "development", "testing", "code_review", "maintenance") for k in range(2)}
    batch = build_batch(_trials(), tasks, {}, "m1-test", n=40, key_dir=tmp_path / "keys", out_dir=rev / "rating",
                        exclude_tasks=["testing-0"])
    return tmp_path, rev, batch


def test_batch_is_blind_paired_and_excludes(setup):
    tmp, rev, batch = setup
    raw = (rev / "rating" / "m1-test.json").read_text(encoding="utf-8")
    assert "system_" not in raw and "baseline_" not in raw            # no system identity in the rater file
    key = json.loads((tmp / "keys" / "m1-test_key.json").read_text(encoding="utf-8"))
    assert len(key) == 40 and all(v["task_id"] != "testing-0" for v in key.values())
    assert all(not (v["system_id"] == "system_e" and v["task_id"].endswith("1")) for v in key.values())  # no refusals
    assert {tuple(u.raters) for u in batch.units} == set(PAIRS)
    tasks = {v["task_id"]: {"query": "q", "ground_truth": "g"} for v in key.values()}
    with pytest.raises(ReviewError, match="never rewritten"):
        build_batch(_trials(), tasks, {}, "m1-test", n=40, key_dir=tmp / "keys", out_dir=rev / "rating")


def test_rating_rules(setup):
    tmp, rev, batch = setup
    rs = RatingStore(rev)
    b, u = rs.next_unit("Sanvi")
    rs.rate(u.blind_id, "Sanvi", 4, 3, True)
    with pytest.raises(ReviewError, match="already rated"):
        rs.rate(u.blind_id, "Sanvi", 4, 3, True)
    outsider = next(r for r in ("Aayan", "Radhesh", "Avaneesh") if r not in " ".join(u.raters))
    with pytest.raises(ReviewError, match="assigned"):
        rs.rate(u.blind_id, outsider, 4, 3, True)
    assert rs.next_unit("Sanvi")[1].blind_id != u.blind_id


def test_candidate_measures():
    from experiments.m1_selection import ref_recall, semantic, token_f1

    ref = ["url_for delegates to current_app url_for and builds with the url adapter"]
    full = "It delegates to current_app.url_for, which builds with the URL adapter; url_for is a helper."
    assert ref_recall(full, ref) > ref_recall("Something unrelated about sessions.", ref)
    assert 0 <= token_f1(full, ref) <= 1
    fake = lambda t: [1.0, 0.0] if "adapter" in t else [0.0, 1.0]
    assert semantic(full, ref, embed=fake) == pytest.approx(1.0)


def test_selection_picks_best_agreement_and_threshold():
    from experiments.m1_selection import best_threshold, select

    units = [{"blind_id": f"H{i:03d}"} for i in range(10)]
    human = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    ratings = []
    for i, h in enumerate(human):
        for rater in ("A", "B"):
            ratings.append({"blind_id": f"H{i:03d}", "rater": rater, "correctness": h, "accept": h >= 4})
    good = [h / 5 for h in human]                      # monotone with the humans
    noise = [0.3, 0.9, 0.1, 0.7, 0.5, 0.2, 0.8, 0.4, 0.6, 0.0]
    res = select(units, ratings, {"good": good, "noise": noise})
    assert res["chosen"] == "good" and res["candidates"]["good"]["spearman_rho"] == pytest.approx(1.0)
    assert res["inter_rater"]["weighted_kappa_correctness"] == pytest.approx(1.0)
    assert res["chosen_threshold"] == pytest.approx(0.8) and res["candidates"]["good"]["kappa_at_threshold"] == 1.0
    t, k = best_threshold([0.1, 0.2, 0.9], [False, False, True])
    assert k == 1.0 and t == pytest.approx(0.9)
