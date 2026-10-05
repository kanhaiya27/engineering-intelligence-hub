"""
Engineering Intelligence Hub — Human Evaluation Protocol (Phase-2 M5)
======================================================================
Defines an independent human validation protocol for validating automated
quality metrics on a representative sample of 12 benchmark tasks (2 per SDLC stage).

Evaluation Dimensions (1 to 5 Likert Scale):
  1. Correctness            (Factual precision against software engineering standards)
  2. Groundedness           (Verifiability against retrieved repository artifacts)
  3. Relevance              (Topical alignment with the engineering query)
  4. Evidence Completeness  (Coverage of all necessary implementation details)
  5. Actionability          (Readiness for developer adoption without debugging)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from knowledge.schemas.benchmark import BenchmarkTask


class HumanEvaluationRating(BaseModel):
    """Single human annotator rating on one system response."""
    task_id: str
    system_id: str
    annotator_id: str
    correctness: int = Field(ge=1, le=5, description="1 (Completely Wrong) to 5 (Perfect)")
    groundedness: int = Field(ge=1, le=5, description="1 (Hallucinated) to 5 (Strictly Cited)")
    relevance: int = Field(ge=1, le=5, description="1 (Off-topic) to 5 (Directly Focused)")
    evidence_completeness: int = Field(ge=1, le=5, description="1 (Incomplete) to 5 (Thorough)")
    actionability: int = Field(ge=1, le=5, description="1 (Unusable) to 5 (Production-Ready)")
    notes: Optional[str] = Field(default=None, description="Qualitative feedback / comments")

    model_config = ConfigDict(use_enum_values=True)

    @property
    def normalized_mean_score(self) -> float:
        """Compute normalized composite score in [0.0, 1.0]."""
        raw_avg = (self.correctness + self.groundedness + self.relevance + self.evidence_completeness + self.actionability) / 5.0
        return round((raw_avg - 1.0) / 4.0, 4)


def sample_human_evaluation_tasks(
    tasks: List[BenchmarkTask],
    sample_per_stage: int = 2,
) -> List[BenchmarkTask]:
    """
    Select a representative 12-task sample (sample_per_stage per SDLC stage,
    balanced across repositories and difficulties).
    """
    by_stage: Dict[str, List[BenchmarkTask]] = {}
    for t in tasks:
        stage = t.sdlc_stage.value if hasattr(t.sdlc_stage, "value") else str(t.sdlc_stage)
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(t)

    selected: List[BenchmarkTask] = []
    for stage, stage_tasks in sorted(by_stage.items()):
        # Select 1 Flask and 1 FastAPI task
        flask_tasks = [t for t in stage_tasks if "flask" in t.repository.lower()]
        fastapi_tasks = [t for t in stage_tasks if "fastapi" in t.repository.lower()]

        if flask_tasks:
            selected.append(sorted(flask_tasks, key=lambda t: t.task_id)[0])
        if fastapi_tasks:
            selected.append(sorted(fastapi_tasks, key=lambda t: t.task_id)[0])

    return selected[: sample_per_stage * 6]


# ---------------------------------------------------------------------------
# Blind rating subset (master prompt Step 1e): 30-50 answers rated by people, used to check
# whether the lexical correctness F1 and the citation-span measures agree with human judgement.
# Raters never see which system wrote an answer.
# ---------------------------------------------------------------------------

import csv  # noqa: E402
import random  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Sequence, Tuple  # noqa: E402

RATING_DIMENSIONS = ("correctness", "groundedness", "relevance", "evidence_completeness", "actionability")


def sample_rating_units(trials: Sequence[Dict[str, Any]], n: int = 40, seed: int = 42) -> List[Dict[str, Any]]:
    """Pick n (task, system) answers, trial 0 only, spread round-robin over SDLC stage x system.

    Each trial dict needs: task_id, system_id, trial_index, sdlc_stage, generated_answer.
    Returns units with a blind id (H001...) in shuffled order.
    """
    if not 30 <= n <= 50:
        raise ValueError("the human-rated subset is 30-50 answers")
    rng = random.Random(seed)
    pool: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for t in trials:
        if t["trial_index"] == 0:
            pool.setdefault((t["sdlc_stage"], t["system_id"]), []).append(t)
    for v in pool.values():
        rng.shuffle(v)
    strata = sorted(pool)
    rng.shuffle(strata)
    chosen, seen = [], set()
    while len(chosen) < n and any(pool.values()):
        for key in strata:
            while pool[key]:
                t = pool[key].pop()
                if (t["task_id"], t["system_id"]) not in seen:
                    seen.add((t["task_id"], t["system_id"]))
                    chosen.append(t)
                    break
            if len(chosen) == n:
                break
    if len(chosen) < n:
        raise ValueError(f"only {len(chosen)} distinct answers available, need {n}")
    rng.shuffle(chosen)
    return [{**t, "blind_id": f"H{i:03d}"} for i, t in enumerate(chosen, start=1)]


def write_blind_sheet(units: Sequence[Dict[str, Any]], tasks: Dict[str, Dict[str, Any]],
                      sheet_path: Path, key_path: Path) -> None:
    """Rater sheet (no system names) + a separate key file mapping blind ids to task/system."""
    with Path(sheet_path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["blind_id", "question", "reference_answer", "answer_to_rate", *RATING_DIMENSIONS, "rater", "notes"])
        for u in units:
            t = tasks[u["task_id"]]
            w.writerow([u["blind_id"], t["query"], t["ground_truth"], u["generated_answer"], *[""] * 5, "", ""])
    with Path(key_path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["blind_id", "task_id", "system_id", "trial_index"])
        for u in units:
            w.writerow([u["blind_id"], u["task_id"], u["system_id"], u["trial_index"]])


def load_ratings(sheet_paths: Sequence[Path], key_path: Path) -> List[HumanEvaluationRating]:
    """Ratings from filled sheets; rows with any empty dimension are skipped, never filled."""
    with Path(key_path).open(newline="", encoding="utf-8") as fh:
        key = {r["blind_id"]: r for r in csv.DictReader(fh)}
    out: List[HumanEvaluationRating] = []
    for path in sheet_paths:
        with Path(path).open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if not row.get("rater") or any(not (row.get(d) or "").strip() for d in RATING_DIMENSIONS):
                    continue
                k = key[row["blind_id"]]
                out.append(HumanEvaluationRating(task_id=k["task_id"], system_id=k["system_id"],
                                                 annotator_id=row["rater"].strip(), notes=row.get("notes") or None,
                                                 **{d: int(row[d]) for d in RATING_DIMENSIONS}))
    return out


def metric_agreement(ratings: Sequence[HumanEvaluationRating], metric: Dict[Tuple[str, str], float],
                     dimension: str = "correctness") -> Dict[str, Any]:
    """Spearman rho and Kendall tau between the mean human rating and an automatic metric.

    `metric[(task_id, system_id)]` is the automatic score of the rated answer (None entries skipped).
    """
    from scipy.stats import kendalltau, spearmanr

    by_unit: Dict[Tuple[str, str], List[int]] = {}
    for r in ratings:
        by_unit.setdefault((r.task_id, r.system_id), []).append(getattr(r, dimension))
    pairs = [(sum(v) / len(v), metric[k]) for k, v in by_unit.items() if metric.get(k) is not None]
    if len(pairs) < 3:
        return {"n": len(pairs), "spearman_rho": None, "kendall_tau": None}
    h, m = zip(*pairs)
    rho, p_rho = spearmanr(h, m)
    tau, p_tau = kendalltau(h, m)
    return {"n": len(pairs), "spearman_rho": float(rho), "spearman_p": float(p_rho),
            "kendall_tau": float(tau), "kendall_p": float(p_tau)}


def inter_rater_agreement(ratings: Sequence[HumanEvaluationRating], dimension: str = "correctness") -> Dict[str, Any]:
    """Quadratic-weighted Cohen's kappa for every pair of raters over the units both rated."""
    from itertools import combinations

    from sklearn.metrics import cohen_kappa_score

    by_rater: Dict[str, Dict[Tuple[str, str], int]] = {}
    for r in ratings:
        by_rater.setdefault(r.annotator_id, {})[(r.task_id, r.system_id)] = getattr(r, dimension)
    out = {}
    for a, b in combinations(sorted(by_rater), 2):
        common = sorted(set(by_rater[a]) & set(by_rater[b]))
        if len(common) >= 2:
            k = cohen_kappa_score([by_rater[a][u] for u in common], [by_rater[b][u] for u in common],
                                  weights="quadratic", labels=[1, 2, 3, 4, 5])
            out[f"{a} vs {b}"] = {"units": len(common), "weighted_kappa": float(k)}
    return out
