"""Tests for the experiment logger."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from experiments.logger import ExperimentLogger


class TestExperimentLogger:
    def test_logger_creates_directory(self, tmp_path):
        logger = ExperimentLogger(
            experiment_id="test-exp-001",
            results_dir=tmp_path,
        )
        assert (tmp_path / "test-exp-001").is_dir()
        logger.close()

    def test_log_config_creates_jsonl_and_json(self, tmp_path):
        logger = ExperimentLogger("test-exp-002", results_dir=tmp_path)
        config = {"model_id": "gpt-4o-mini", "retrieval_strategy": "hybrid"}
        logger.log_config(config)
        logger.close()

        # JSONL events file
        events_path = tmp_path / "test-exp-002" / "events.jsonl"
        assert events_path.exists()
        with open(events_path) as f:
            line = json.loads(f.readline())
        assert line["event_type"] == "experiment_config"
        assert line["model_id"] == "gpt-4o-mini"

        # Standalone config.json
        config_path = tmp_path / "test-exp-002" / "config.json"
        assert config_path.exists()

    def test_log_result(self, tmp_path):
        with ExperimentLogger("test-exp-003", results_dir=tmp_path) as logger:
            logger.log_result({
                "result_id": "r-001",
                "task_id": "t-001",
                "quality_score": 0.82,
            })

        events = ExperimentLogger("test-exp-003", results_dir=tmp_path).read_events()
        result_events = [e for e in events if e.get("event_type") == "task_result"]
        assert len(result_events) == 1
        assert result_events[0]["quality_score"] == 0.82

    def test_log_escalation(self, tmp_path):
        with ExperimentLogger("test-exp-004", results_dir=tmp_path) as logger:
            logger.log_escalation(
                task_id="t-001",
                attempt=1,
                reason="quality < threshold",
                from_model="gpt-4o-mini",
                to_model="gpt-4o",
                quality_score_before=0.60,
            )

        with ExperimentLogger("test-exp-004", results_dir=tmp_path) as logger:
            events = logger.read_events()
        esc_events = [e for e in events if e.get("event_type") == "escalation"]
        assert len(esc_events) == 1
        assert esc_events[0]["from_model"] == "gpt-4o-mini"
        assert esc_events[0]["to_model"] == "gpt-4o"

    def test_experiment_start_end(self, tmp_path):
        with ExperimentLogger("test-exp-005", results_dir=tmp_path) as logger:
            logger.log_experiment_start()
            logger.log_experiment_end(total_tasks=10, successful_tasks=9)

        with ExperimentLogger("test-exp-005", results_dir=tmp_path) as logger:
            events = logger.read_events()
        types = [e["event_type"] for e in events]
        assert "experiment_start" in types
        assert "experiment_end" in types

    def test_context_manager_closes_file(self, tmp_path):
        logger = ExperimentLogger("test-exp-006", results_dir=tmp_path)
        with logger:
            logger.log_custom("ping", value=1)
        assert logger._file.closed

    def test_timestamps_present(self, tmp_path):
        with ExperimentLogger("test-exp-007", results_dir=tmp_path) as logger:
            logger.log_custom("test_event", foo="bar")

        with ExperimentLogger("test-exp-007", results_dir=tmp_path) as logger:
            events = logger.read_events()
        assert "timestamp" in events[0]
        assert events[0]["experiment_id"] == "test-exp-007"
