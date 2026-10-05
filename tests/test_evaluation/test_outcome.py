"""Tests for the independent outcome measures (evaluation/outcome.py) and the human-rating tools."""

from __future__ import annotations

import pytest

from evaluation.outcome import outcome, parse_citations, rates
from evaluation.retrieval_metrics import Label, Span

LAB = Label(task_id="t", relevant_files=["src/flask/ctx.py", "docs/a.md"],
            spans=[Span("src/flask/ctx.py", 367, 394), Span("src/flask/ctx.py", 396, 431)])


def test_parse_strict_citations():
    lines, files = parse_citations(
        "Push [`src/flask/ctx.py:L367-L394`] and [src/flask/ctx.py:L400] see [docs/a.md]. "
        "Not a citation: app.route, e.g. ```[x/y.py:L1-L2]```")
    assert lines == [("src/flask/ctx.py", 367, 394), ("src/flask/ctx.py", 400, 400)]
    assert files == ["docs/a.md"]


def test_supported_answer():
    o = outcome("It pushes [src/flask/ctx.py:L370-L380] then [src/flask/app.py:L1-L5].", LAB)
    assert o.supported is True and o.unsupported is False
    assert o.cited_span_precision == 0.5 and o.cited_span_recall == 0.5
    assert o.cited_file_recall == 0.5


def test_uncited_and_wrongly_cited_answers_are_unsupported():
    assert outcome("It pushes the context.", LAB).unsupported is True
    o = outcome("See [src/flask/ctx.py:L1-L10].", LAB)
    assert o.unsupported is True and o.cited_span_precision == 0.0


def test_refusal_is_neither_supported_nor_unsupported():
    o = outcome("INSUFFICIENT EVIDENCE: nothing found.", LAB)
    assert o.refusal and o.supported is None and o.unsupported is None


def test_no_label_leaves_everything_missing():
    o = outcome("See [src/flask/ctx.py:L370-L380].", None)
    assert not o.has_label and o.supported is None and o.cited_span_precision is None
    assert o.line_citations == 1


def test_rates():
    outs = [outcome("[src/flask/ctx.py:L370-L371]", LAB), outcome("nothing cited", LAB),
            outcome("INSUFFICIENT EVIDENCE", LAB), outcome("[src/flask/ctx.py:L370-L371]", None)]
    r = rates(outs)
    assert r.trials == 4 and r.no_label == 1 and r.refusals == 1 and r.refusal_rate == 0.25
    assert r.answered_with_label == 2 and r.unsupported == 1 and r.unsupported_rate == 0.5
    assert r.answers_with_line_citations == 1 and r.mean_cited_span_precision == 1.0


def test_outcome_takes_no_retrieved_chunks():
    """The outcome sees only the answer and the label, never what the system retrieved."""
    import inspect

    assert list(inspect.signature(outcome).parameters) == ["answer", "label"]


def test_runner_records_independent_outcome():
    from experiments.m5.runner import M5BenchmarkRunner
    from knowledge.schemas.benchmark import BenchmarkTask
    from knowledge.schemas.tasks import EngTaskResponse, RetrievalResult

    task = BenchmarkTask(task_id="eih-phase1-code-011", sdlc_stage="architecture", task_type="code_explanation",
                         difficulty="medium", complexity="medium", criticality="medium", repository="pallets/flask",
                         query="q", ground_truth="push and pop", expected_quality_threshold=0.6)
    runner = M5BenchmarkRunner(provider_name="mock")
    resp = EngTaskResponse(task_id=task.task_id, answer="Push [src/flask/ctx.py:L370-L380].",
                           retrieval=RetrievalResult(task_id=task.task_id, strategy_used="h", chunks=[]),
                           latency_ms=1.0, energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0)
    trial = runner._evaluate_trial("system_c", task, resp, trial_index=0, split_name="val")
    assert trial.has_retrieval_label and trial.answer_supported is True and trial.line_citations == 1


# --- human rating subset ------------------------------------------------------------------

STAGES = ("requirements", "architecture", "development", "testing", "code_review", "maintenance")
SYSTEMS = ("baseline_a", "baseline_b", "system_c", "system_d", "system_e", "system_e_routed")


def _trials():
    return [{"task_id": f"{stage}-{k}", "system_id": sysid, "trial_index": 0, "sdlc_stage": stage,
             "generated_answer": f"ans {stage} {sysid} {k}"}
            for stage in STAGES for sysid in SYSTEMS for k in range(2)]


def test_sample_rating_units_is_stratified_blind_and_deterministic():
    from experiments.m5.human_eval import sample_rating_units

    a = sample_rating_units(_trials(), n=36, seed=42)
    assert a == sample_rating_units(_trials(), n=36, seed=42)
    assert len({(u["task_id"], u["system_id"]) for u in a}) == 36
    assert {u["sdlc_stage"] for u in a} == set(STAGES)
    assert [u["blind_id"] for u in a] == [f"H{i:03d}" for i in range(1, 37)]
    with pytest.raises(ValueError):
        sample_rating_units(_trials(), n=20)


def test_blind_sheet_hides_system_and_round_trips(tmp_path):
    import csv

    from experiments.m5.human_eval import load_ratings, sample_rating_units, write_blind_sheet

    units = sample_rating_units(_trials(), n=30)
    tasks = {u["task_id"]: {"query": "q", "ground_truth": "gt"} for u in units}
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.csv"
    write_blind_sheet(units, tasks, sheet, key)
    assert "system" not in sheet.read_text(encoding="utf-8").splitlines()[0]
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    rows[0].update(correctness="4", groundedness="3", relevance="5", evidence_completeness="2",
                   actionability="3", rater="Sanvi")
    rows[1].update(correctness="4", rater="Aayan")  # incomplete row: skipped, not filled
    with sheet.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    got = load_ratings([sheet], key)
    assert len(got) == 1 and got[0].annotator_id == "Sanvi" and got[0].system_id == units[0]["system_id"]


def test_metric_and_inter_rater_agreement():
    from experiments.m5.human_eval import HumanEvaluationRating, inter_rater_agreement, metric_agreement

    def r(task, rater, c):
        return HumanEvaluationRating(task_id=task, system_id="s", annotator_id=rater, correctness=c,
                                     groundedness=3, relevance=3, evidence_completeness=3, actionability=3)

    ratings = [r(f"t{i}", "A", c) for i, c in enumerate([1, 2, 3, 4, 5])] + \
              [r(f"t{i}", "B", c) for i, c in enumerate([1, 2, 3, 4, 5])]
    m = {(f"t{i}", "s"): x for i, x in enumerate([0.1, 0.2, 0.3, 0.4, 0.5])}
    out = metric_agreement(ratings, m)
    assert out["n"] == 5 and out["spearman_rho"] == pytest.approx(1.0) and out["kendall_tau"] == pytest.approx(1.0)
    assert inter_rater_agreement(ratings)["A vs B"]["weighted_kappa"] == pytest.approx(1.0)


def test_grounded_success_needs_correct_and_cited_labelled_evidence():
    """A2: success = correct (F1 >= task threshold) AND cites a labelled evidence span."""
    from experiments.m5.runner import M5BenchmarkRunner
    from knowledge.schemas.benchmark import BenchmarkTask
    from knowledge.schemas.tasks import EngTaskResponse, RetrievalResult

    gt = "RequestContext push and pop manage the request context stack"
    task = BenchmarkTask(task_id="eih-phase1-code-011", sdlc_stage="architecture", task_type="code_explanation",
                         difficulty="medium", complexity="medium", criticality="medium", repository="pallets/flask",
                         query="q", ground_truth=gt, expected_quality_threshold=0.6)
    runner = M5BenchmarkRunner(provider_name="mock")

    def trial(answer):
        resp = EngTaskResponse(task_id=task.task_id, answer=answer,
                               retrieval=RetrievalResult(task_id=task.task_id, strategy_used="h", chunks=[]),
                               latency_ms=1.0, energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0)
        return runner._evaluate_trial("system_c", task, resp, trial_index=0, split_name="val")

    assert trial(gt + " [src/flask/ctx.py:L370-L380]").grounded_success is True
    assert trial(gt + " [src/flask/ctx.py:L1-L5]").grounded_success is False      # cites outside the label
    assert trial(gt).grounded_success is False                                     # correct but uncited
    assert trial("Something else [src/flask/ctx.py:L370-L380]").grounded_success is False  # cited, wrong
    assert trial("INSUFFICIENT EVIDENCE").grounded_success is False                # refusal of answerable task
