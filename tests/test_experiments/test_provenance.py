"""Tests for the provenance block every result file must carry."""

from __future__ import annotations

from experiments import provenance


def test_provenance_has_required_fields(monkeypatch):
    monkeypatch.setattr(provenance, "ollama_info", lambda: {"version": "x", "models": {"m": {"digest": "abc"}}})
    p = provenance.collect_provenance()
    for key in ("machine_id", "gpu", "torch", "ollama", "git", "sustainability_config", "recorded_at_utc"):
        assert key in p
    assert set(p["git"]) == {"sha", "branch", "dirty"}
    assert p["ollama"]["models"]["m"]["digest"] == "abc"
    assert {"torch", "cuda"} <= set(p["torch"])


def test_ollama_info_records_error_instead_of_guessing():
    info = provenance.ollama_info(base_url="http://127.0.0.1:9", timeout=0.5)
    assert info["version"] is None and info["models"] == {}
    assert "error" in info


def test_machine_id_setting_reads_env(monkeypatch):
    from core.config import Settings

    monkeypatch.setenv("EIH_MACHINE_ID", "laptop-z")
    assert Settings().machine_id == "laptop-z"
