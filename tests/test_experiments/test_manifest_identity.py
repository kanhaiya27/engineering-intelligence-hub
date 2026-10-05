"""Manifest binds retrieval config, collection, graph build and data files (Step 1g)."""

from __future__ import annotations

import json

import pytest

from experiments.m5 import manifest as mf


def test_static_identity_is_in_every_manifest():
    fv = mf.ExperimentManifest.create_default().frozen_variables
    for field in ("retrieval_config_sha256", "inference_config_sha256", "models_config_sha256",
                  "benchmark_tasks_sha256", "benchmark_splits_sha256", "retrieval_labels_sha256",
                  "graph_build_report_sha256"):
        assert getattr(fv, field, None) and getattr(fv, field).startswith("sha256:"), field
    assert fv.vector_collection == "eih_knowledge_v2"
    assert fv.collection_points is None  # live fields only with live=True


def test_changed_retrieval_config_is_refused():
    m = mf.ExperimentManifest.create_default()
    m.frozen_variables.retrieval_config_sha256 = "sha256:old"
    assert [x["field"] for x in mf.runtime_mismatches(m)] == ["retrieval_config_sha256"]


def test_hash_changes_with_data_identity():
    a = mf.ExperimentManifest.create_default()
    b = a.model_copy(deep=True)
    b.frozen_variables.benchmark_tasks_sha256 = "sha256:other"
    assert a.compute_hash() != b.compute_hash()


@pytest.fixture
def fake_live(monkeypatch, tmp_path):
    report = tmp_path / "graph_build_wave1.json"
    report.write_text(json.dumps({"results": {"read_back": {"nodes": 100, "edges": 50}}}), encoding="utf-8")
    monkeypatch.setattr(mf, "graph_build_report", lambda: report)
    state = {"collection_points": 10, "graph_nodes": 100, "graph_edges": 50}
    monkeypatch.setattr(mf, "live_data_identity", lambda: dict(state))
    return state


def test_live_check_passes_on_the_built_graph(fake_live):
    m = mf.ExperimentManifest.create_default(live=True)
    assert m.frozen_variables.graph_nodes == 100
    assert mf.runtime_mismatches(m, live=True) == []


def test_live_check_refuses_a_graph_changed_after_its_build(fake_live):
    m = mf.ExperimentManifest.create_default(live=True)
    fake_live.update(graph_nodes=102, graph_edges=51)  # e.g. a test wrote fixture nodes into Neo4j
    fields = {x["field"] for x in mf.runtime_mismatches(m, live=True)}
    assert {"graph_nodes", "graph_edges", "graph_vs_build_report"} <= fields


def test_live_check_refuses_a_static_manifest(fake_live):
    m = mf.ExperimentManifest.create_default()  # frozen without live identity
    assert {x["field"] for x in mf.runtime_mismatches(m, live=True)} == set(mf.LIVE_FIELDS)
