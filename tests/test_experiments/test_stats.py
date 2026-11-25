"""Tests for experiments/stats.py and CO2e per successful task (experiments/m5/analysis.py)."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from experiments import stats


def _t(system, task, value, **kw):
    return SimpleNamespace(system_id=system, task_id=task, v=value, **kw)


def test_task_means_average_trials_and_skip_missing():
    trials = [_t("a", "t1", 1.0), _t("a", "t1", 0.0), _t("a", "t2", None), _t("b", "t1", 0.5)]
    assert stats.task_means(trials, lambda t: t.v) == {"a": {"t1": 0.5}, "b": {"t1": 0.5}}


def test_paired_comparison_matches_scipy_and_hand_values():
    from scipy.stats import wilcoxon

    a = {f"t{i}": x for i, x in enumerate([0.2, 0.4, 0.1, 0.5, 0.3, 0.6, 0.2, 0.4])}
    b = {f"t{i}": x for i, x in enumerate([0.5, 0.45, 0.3, 0.55, 0.2, 0.9, 0.6, 0.41])}
    r = stats.paired_comparison(a, b, n_resamples=2000)
    diffs = [b[k] - a[k] for k in sorted(a)]
    assert r["n_tasks"] == 8 and r["mean_diff"] == pytest.approx(sum(diffs) / 8)
    assert r["wilcoxon_p"] == pytest.approx(wilcoxon(diffs).pvalue)
    lo, hi = r["ci95"]
    assert lo <= r["mean_diff"] <= hi
    sd = math.sqrt(sum((d - r["mean_diff"]) ** 2 for d in diffs) / 7)
    assert r["cohens_dz"] == pytest.approx(r["mean_diff"] / sd)


def test_paired_comparison_drops_unpaired_tasks_and_handles_identical():
    r = stats.paired_comparison({"t1": 1.0, "t2": 1.0, "t3": 0.0}, {"t1": 1.0, "t2": 1.0})
    assert r["n_tasks"] == 2 and r["dropped_tasks"] == 1
    assert r["wilcoxon_p"] == 1.0 and r["rank_biserial"] is None


def test_rank_biserial():
    assert stats.rank_biserial([1, 2, 3]) == 1.0
    assert stats.rank_biserial([1, -2]) == pytest.approx(-1 / 3)
    assert stats.rank_biserial([0, 0]) is None


def test_bootstrap_ci_is_deterministic_and_brackets_mean():
    v = [0.1, 0.4, 0.35, 0.8, 0.2, 0.6]
    assert stats.bootstrap_ci(v, n_resamples=1000) == stats.bootstrap_ci(v, n_resamples=1000)
    lo, hi = stats.bootstrap_ci(v, n_resamples=1000)
    assert lo < sum(v) / len(v) < hi


def test_holm_known_values():
    adj = stats.holm({"x": 0.01, "y": 0.04, "z": 0.03, "w": None})
    assert adj["x"] == pytest.approx(0.03) and adj["z"] == pytest.approx(0.06)
    assert adj["y"] == pytest.approx(0.06) and adj["w"] is None  # monotone


def test_mcnemar_exact():
    a = {f"t{i}": i < 2 for i in range(10)}          # a succeeds on t0, t1
    b = {f"t{i}": i >= 2 for i in range(10)}         # b succeeds on t2..t9
    r = stats.mcnemar_exact(a, b)
    assert r["b_only_success"] == 8 and r["a_only_success"] == 2
    assert r["p"] == pytest.approx(0.109375)


def test_compare_ladder_holm_family():
    per = {s: {f"t{i}": base + 0.1 * (i % 3) for i in range(10)}
           for s, base in (("baseline_a", 0.1), ("baseline_b", 0.3), ("system_c", 0.3))}
    per["system_c"] = {k: v + (0.05 if k != "t0" else -0.01) for k, v in per["baseline_b"].items()}
    res = stats.compare_ladder(per)
    assert set(res) == {"A->B", "B->C"}
    for r in res.values():
        assert r["wilcoxon_p_holm"] >= r["wilcoxon_p"]


def test_stratified_and_mixed_effects_detect_interaction():
    import random

    rng = random.Random(1)
    per = {"system_c": {}, "system_d": {}}
    strata = {}
    for i in range(40):
        t, s = f"t{i}", ("architecture" if i % 2 else "testing")
        strata[t] = s
        base = rng.random() * 0.2
        per["system_c"][t] = base + rng.gauss(0, 0.01)
        per["system_d"][t] = base + (0.3 if s == "architecture" else 0.0) + rng.gauss(0, 0.01)
    st = stats.stratified(per, strata, "system_c", "system_d", n_resamples=500)
    assert st["architecture"]["mean_diff"] > 0.25 and abs(st["testing"]["mean_diff"]) < 0.05
    me = stats.mixed_effects(per, strata, ["system_c", "system_d"])
    assert me["n_tasks"] == 40 and me["interaction_wald"]["p"] < 0.001


def test_min_detectable_effect():
    mde = stats.min_detectable_effect(24, 0.2)
    assert mde == pytest.approx((1.959964 + 0.841621) * 0.2 / math.sqrt(24 * 0.955), rel=1e-4)
    assert stats.min_detectable_effect(1, 0.2) is None


# --- CO2e per successful task -----------------------------------------------------------


def _trial(system, co2e, success, load_j=None, loads=0):
    return SimpleNamespace(system_id=system, co2e_grams=co2e, grounded_success=success,
                           quality_constrained_success=None, model_load_energy_joules=load_j, model_loads=loads)


def test_co2e_per_successful_task_counts_every_trial_and_loads():
    from experiments.m5.analysis import co2e_per_successful_task

    trials = [_trial("e", 0.10, True), _trial("e", 0.20, False), _trial("e", 0.30, None, load_j=3600.0, loads=1),
              _trial("e", 0.40, True)]
    r = co2e_per_successful_task(trials, carbon_intensity_gco2_per_kwh=713.0)
    # numerator: 1.0 g of trials + 3600 J = 0.001 kWh x 713 = 0.713 g of model load
    assert r["total_co2e_grams"] == pytest.approx(1.713)
    assert r["successful_trials"] == 2 and r["trials_success_unknown"] == 1
    assert r["co2e_grams_per_successful_task"] == pytest.approx(1.713 / 2)
    assert r["success_rate"] == 0.6667 and r["model_loads"] == 1


def test_co2e_per_successful_task_undefined_without_success():
    from experiments.m5.analysis import co2e_per_successful_task, co2e_per_successful_task_by_system

    assert co2e_per_successful_task([_trial("a", 0.1, False)], 713.0)["co2e_grams_per_successful_task"] is None
    by = co2e_per_successful_task_by_system([_trial("a", 0.1, True), _trial("b", 0.2, True)], 713.0)
    assert set(by) == {"a", "b"}
