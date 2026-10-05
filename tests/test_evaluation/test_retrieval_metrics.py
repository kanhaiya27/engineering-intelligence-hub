"""Unit tests for Mode R retrieval metrics (evaluation/retrieval_metrics.py), hand-computed values."""

from __future__ import annotations

import json
import math

import pytest

from evaluation.retrieval_metrics import (
    Label, RetrievedItem, Span, file_level, mean_metrics, primary_of, span_level,
)

L2 = math.log2


def _label(**kw):
    base = dict(task_id="t", relevant_files=["a.py", "b.py"],
                spans=[Span("a.py", 10, 20), Span("b.py", 1, 5)], n_relevant_chunks=3)
    return Label(**{**base, **kw})


def test_file_level_hand_computed():
    items = [RetrievedItem("x.py"), RetrievedItem("a.py"), RetrievedItem("a.py"), RetrievedItem("y.py"),
             RetrievedItem("b.py")]
    m = file_level(items, _label(), ks=(1, 3, 5))
    # ranked files: x, a, y, b  (duplicate a dropped)
    assert m["n_ranked"] == 4
    assert m["mrr"] == pytest.approx(1 / 2)
    assert m["recall@1"] == 0 and m["recall@3"] == pytest.approx(1 / 2) and m["recall@5"] == 1.0
    assert m["precision@1"] == 0 and m["precision@3"] == pytest.approx(1 / 3) and m["precision@5"] == pytest.approx(2 / 5)
    dcg3, idcg3 = 1 / L2(3), 1 + 1 / L2(3)
    assert m["ndcg@3"] == pytest.approx(dcg3 / idcg3)
    dcg5 = 1 / L2(3) + 1 / L2(5)
    assert m["ndcg@5"] == pytest.approx(dcg5 / idcg3)


def test_file_level_perfect_and_empty():
    perfect = file_level([RetrievedItem("a.py"), RetrievedItem("b.py")], _label(), ks=(2, 10))
    assert perfect["recall@2"] == perfect["ndcg@2"] == perfect["mrr"] == 1.0
    assert perfect["precision@10"] == pytest.approx(0.2)  # denominator is K, not the number returned
    empty = file_level([], _label(), ks=(5,))
    assert empty["recall@5"] == empty["ndcg@5"] == empty["mrr"] == empty["precision@5"] == 0.0


def test_alternative_file_counts_as_its_primary_once():
    lab = _label(relevant_files=["d/tutorial004.py", "doc.md"], spans=[Span("doc.md", 1, 2)],
                 alternative_files=["d/tutorial004_an_py310.py", "d/tutorial004_py310.py"])
    m = file_level([RetrievedItem("d/tutorial004_an_py310.py"), RetrievedItem("d/tutorial004.py"),
                    RetrievedItem("doc.md")], lab, ks=(3,))
    assert m["recall@3"] == 1.0
    assert m["precision@3"] == 1.0  # all three are relevant files
    # gains 1, 0 (primary already found), 1
    assert m["ndcg@3"] == pytest.approx((1 + 1 / L2(4)) / (1 + 1 / L2(3)))


def test_primary_of_requires_unique_match():
    assert primary_of("d/t004_an.py", ["d/t004.py", "e/t004.py"]) == "d/t004.py"
    with pytest.raises(ValueError):
        primary_of("d/zzz.py", ["d/t004.py"])


def test_span_level_hand_computed():
    items = [
        RetrievedItem("a.py", 1, 9),     # touches no span (ends before 10)
        RetrievedItem("a.py", 18, 30),   # overlaps span 0
        RetrievedItem("b.py", 5, 9),     # overlaps span 1 at line 5
        RetrievedItem("a.py", 12, 14),   # overlaps span 0 again
    ]
    m = span_level(items, _label(), ks=(1, 2, 4))
    assert m["mrr"] == pytest.approx(1 / 2)
    assert m["recall@1"] == 0 and m["recall@2"] == pytest.approx(1 / 2) and m["recall@4"] == 1.0
    assert m["precision@4"] == pytest.approx(3 / 4)
    # R = 3 relevant chunks in the index; gains 0,1,1,1 at K=4 ; IDCG@4 = three hits first
    dcg = 1 / L2(3) + 1 / L2(4) + 1 / L2(5)
    idcg = 1 + 1 / L2(3) + 1 / L2(4)
    assert m["ndcg@4"] == pytest.approx(dcg / idcg)


def test_one_chunk_can_cover_two_spans():
    lab = _label(relevant_files=["a.py"], spans=[Span("a.py", 1, 5), Span("a.py", 8, 9)], n_relevant_chunks=1)
    m = span_level([RetrievedItem("a.py", 1, 20)], lab, ks=(1,))
    assert m["recall@1"] == 1.0 and m["ndcg@1"] == 1.0 and m["precision@1"] == 1.0


def test_graph_chunks_excluded_at_span_level_unless_asked_but_count_for_files():
    g = RetrievedItem("b.py", 1, 5, is_graph=True)
    items = [g, RetrievedItem("a.py", 10, 11)]
    assert span_level(items, _label(), ks=(1,))["recall@1"] == pytest.approx(1 / 2)  # graph chunk skipped
    assert span_level(items, _label(), ks=(1,), include_graph=True)["recall@1"] == pytest.approx(1 / 2)
    assert span_level(items, _label(), ks=(1,), include_graph=True)["mrr"] == 1.0
    assert file_level(items, _label(), ks=(1,))["mrr"] == 1.0


def test_chunk_without_lines_never_matches_a_span():
    assert span_level([RetrievedItem("a.py")], _label(), ks=(1,))["recall@1"] == 0.0


def test_windows_paths_normalised():
    assert file_level([RetrievedItem("a.py".replace("/", "\\"))], _label(), ks=(1,))["mrr"] == 1.0
    assert file_level([RetrievedItem("src\\a.py")], _label(relevant_files=["src/a.py"],
                      spans=[Span("src/a.py", 1, 2)]), ks=(1,))["mrr"] == 1.0


def test_dot_directories_kept():
    lab = _label(relevant_files=[".github/workflows/ci.yml"], spans=[Span(".github/workflows/ci.yml", 1, 2)])
    assert file_level([RetrievedItem("./.github/workflows/ci.yml")], lab, ks=(1,))["mrr"] == 1.0
    assert file_level([RetrievedItem("github/workflows/ci.yml")], lab, ks=(1,))["mrr"] == 0.0


def test_mean_metrics():
    assert mean_metrics([{"mrr": 1.0}, {"mrr": 0.0}]) == {"mrr": 0.5}
    assert mean_metrics([]) == {}


def test_every_dev_val_label_loads_and_a_perfect_ranking_scores_one():
    from benchmark.retrieval_labels import LABELS_PATH

    for d in json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]:
        lab = Label.from_json(d)
        assert lab.n_relevant_chunks and lab.n_relevant_chunks >= 1
        for alt in lab.alternative_files:
            primary_of(alt, lab.relevant_files)
        ideal = [RetrievedItem(s.file, s.start_line, s.end_line) for s in lab.spans]
        k = len(ideal)
        assert span_level(ideal, lab, ks=(k,))[f"recall@{k}"] == 1.0
        assert file_level(ideal, lab, ks=(len(lab.relevant_files),))[f"recall@{len(lab.relevant_files)}"] == 1.0
