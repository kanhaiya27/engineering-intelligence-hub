"""
Regression tests: every settings group must read the project .env file.

Nested settings groups are built through default_factory, so they do not inherit
env_file from the top-level Settings. Before this was fixed, every EIH_<GROUP>_*
value in .env (TDP watts, carbon region, quality threshold, graph password...) was
silently ignored and only real OS environment variables took effect.
"""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from core import config
from core.config import ENV_FILE, Settings

NESTED_GROUPS = [
    name
    for name, field in Settings.model_fields.items()
    if isinstance(field.default_factory, type) and issubclass(field.default_factory, BaseSettings)
]


def test_all_nested_groups_discovered():
    assert {"sustainability", "quality", "retrieval", "graph_store"} <= set(NESTED_GROUPS)


@pytest.mark.parametrize("group", NESTED_GROUPS)
def test_every_group_points_at_project_env_file(group):
    cls = Settings.model_fields[group].default_factory
    assert cls.model_config.get("env_file") == ENV_FILE, f"{cls.__name__} ignores .env"


def test_env_file_value_reaches_nested_group(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "EIH_SUSTAINABILITY_GPU_TDP_WATTS=123.0\n"
        "EIH_QUALITY_MAX_ESCALATION_ATTEMPTS=5\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("EIH_SUSTAINABILITY_GPU_TDP_WATTS", raising=False)
    monkeypatch.delenv("EIH_QUALITY_MAX_ESCALATION_ATTEMPTS", raising=False)

    assert config.SustainabilitySettings(_env_file=str(env)).gpu_tdp_watts == 123.0
    assert config.QualitySettings(_env_file=str(env)).max_escalation_attempts == 5


def test_os_environment_still_overrides_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("EIH_SUSTAINABILITY_GPU_TDP_WATTS=123.0\n", encoding="utf-8")
    monkeypatch.setenv("EIH_SUSTAINABILITY_GPU_TDP_WATTS", "77.0")

    assert config.SustainabilitySettings(_env_file=str(env)).gpu_tdp_watts == 77.0
