"""
Power check (Step 3d): minimum detectable effect (MDE) per RQ comparison at real sample sizes.

Variation comes from the Step 2c dev/val run (36 tasks, 3 trials, task-level means). Dev/val
is used only to estimate spread, never to pick anything about the test set.

  continuous  MDE of the mean paired difference: two-sided alpha 0.05, power 0.80, paired Wilcoxon
              (normal approximation scaled by its 0.955 efficiency): experiments.stats
  binary      MDE of the difference in paired proportions with McNemar's test, normal
              approximation, at the observed share of discordant tasks

Sizes:
  * 24, the pilot test split as it is today;
  * the test split if the review queue reaches 150 / 300 / 390 new approved tasks
    (40% go to test), i.e. 84 / 144 / 180;
  * per SDLC stage, each of those divided by 6 (RQ5).

    python -m experiments.power_check --run-id power-2026-10-06
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "power"
RUNS = ("modeq-val-2c-2026-10-06", "modeq-dev-2c-2026-10-06")
SIZES = {"pilot test today": 24, "+150 approved": 24 + 60, "+300 approved": 24 + 120, "+390 approved": 24 + 156}

COMPARISONS = [
    # (RQ, label, system a, system b, metric, kind)
    ("RQ1", "B vs C", "baseline_b", "system_c", "task_correctness", "continuous"),
    ("RQ1", "B vs C", "baseline_b", "system_c", "answer_supported", "binary"),
    ("RQ2", "C vs D", "system_c", "system_d", "task_correctness", "continuous"),
    ("RQ2", "C vs D", "system_c", "system_d", "answer_supported", "binary"),
    ("RQ3", "D vs E", "system_d", "system_e", "answer_supported", "binary"),
    ("RQ3", "D vs E", "system_d", "system_e", "is_grounded_refusal", "binary"),
    ("RQ4", "E vs E+routing", "system_e", "system_e_routed", "gpu_energy_joules", "continuous"),
    ("RQ4", "E vs E+routing", "system_e", "system_e_routed", "answer_supported", "binary"),
]


def mcnemar_mde(n: int, p_disc: float, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Smallest |p_b - p_a| detectable by McNemar at n pairs with discordant share p_disc."""
    from scipy.stats import norm

    if n < 2 or p_disc <= 0:
        return None
    za, zb = norm.ppf(1 - alpha / 2), norm.ppf(power)
    lo, hi = 1e-6, p_disc
    for _ in range(100):
        d = (lo + hi) / 2
        need = (za * math.sqrt(p_disc) + zb * math.sqrt(max(p_disc - d * d, 0))) ** 2 / (d * d)
        lo, hi = (d, hi) if need > n else (lo, d)
    return hi if hi < p_disc else None


def load_task_means() -> Dict[str, Dict[str, Dict[str, float]]]:
    """{system: {metric: {task: mean over trials}}} with booleans as 0/1, None skipped."""
    acc: Dict[tuple, List[float]] = {}
    for run in RUNS:
        for line in (REPO_ROOT / "experiments" / "results" / "queue" / "machine_A" / run / "results.jsonl") \
                .read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            t = rec["result"]
            assert t["dataset_split"] in ("dev", "val")
            for m in ("task_correctness", "answer_supported", "is_grounded_refusal", "gpu_energy_joules"):
                v = t.get(m)
                if v is not None:
                    acc.setdefault((t["system_id"], m, t["task_id"]), []).append(float(v))
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for (s, m, tid), vs in acc.items():
        out.setdefault(s, {}).setdefault(m, {})[tid] = sum(vs) / len(vs)
    return out


def main(argv=None) -> int:
    from experiments.stats import min_detectable_effect

    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    args = p.parse_args(argv)
    tm = load_task_means()
    rows = []
    for rq, label, a, b, metric, kind in COMPARISONS:
        A, B = tm[a][metric], tm[b][metric]
        tasks = sorted(set(A) & set(B))
        if kind == "continuous":
            diffs = [B[t] - A[t] for t in tasks]
            sd = st.stdev(diffs)
            spread = {"sd_paired_diff": sd, "observed_mean_diff_devval": sum(diffs) / len(diffs)}
            mde = {k: min_detectable_effect(n, sd) for k, n in SIZES.items()}
            mde_stage = {k: min_detectable_effect(n // 6, sd) for k, n in SIZES.items()}
        else:
            # majority over trials per task -> paired binary outcome
            a_bin = {t: A[t] >= 0.5 for t in tasks}
            b_bin = {t: B[t] >= 0.5 for t in tasks}
            p_disc = sum(1 for t in tasks if a_bin[t] != b_bin[t]) / len(tasks)
            spread = {"discordant_share": p_disc, "rate_a_devval": sum(a_bin.values()) / len(tasks),
                      "rate_b_devval": sum(b_bin.values()) / len(tasks)}
            mde = {k: mcnemar_mde(n, max(p_disc, 1 / len(tasks))) for k, n in SIZES.items()}
            mde_stage = {k: mcnemar_mde(n // 6, max(p_disc, 1 / len(tasks))) for k, n in SIZES.items()}
        rows.append({"rq": rq, "comparison": label, "metric": metric, "kind": kind, "tasks_devval": len(tasks),
                     **spread, "mde": mde, "mde_per_stage_rq5": mde_stage})
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "runs": list(RUNS), "sizes": SIZES,
           "note": ("task_correctness is plain token F1, which M1 will replace; its MDE shows scale only. "
                    "Binary MDEs use a floor of 1/36 discordant share when none was observed."), "rows": rows}
    out = OUT_ROOT / "machine_A" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "power.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        f = lambda v: "n/a" if v is None else f"{v:.3f}"
        print(f"{r['rq']} {r['comparison']:15} {r['metric']:20} " + " ".join(f"{k}={f(v)}" for k, v in r["mde"].items())
              + " | per stage " + " ".join(f(v) for v in r["mde_per_stage_rq5"].values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
