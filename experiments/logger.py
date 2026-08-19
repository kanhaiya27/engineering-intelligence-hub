"""
Engineering Intelligence Hub — Structured Experiment Logger
===========================================================
Writes experiment events to a JSONL file (one JSON object per line).

Format choice:
- JSONL is append-only, streaming-friendly, and directly loadable by
  pandas, DuckDB, and most analysis tools.
- Each line is a complete, self-contained record.

Log file locations:
  experiments/results/<experiment_id>/events.jsonl
  experiments/results/<experiment_id>/config.json

Schema
------
Every logged event has at minimum:
  {
    "event_type": "...",
    "experiment_id": "...",
    "timestamp": "ISO-8601",
    ... event-specific fields
  }
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.logging import get_logger

logger = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentLogger:
    """
    Writes structured experiment events to a JSONL log file.

    Each ExperimentLogger instance manages one experiment run's log.
    Multiple instances can run concurrently (different experiment IDs).

    Usage
    -----
    logger = ExperimentLogger(experiment_id="eih-baseline-a-20250815")
    logger.log_config(config.model_dump())
    logger.log_result(result.model_dump())
    logger.log_escalation(task_id="...", attempt=1, reason="quality < threshold")
    logger.close()
    """

    def __init__(
        self,
        experiment_id: str,
        results_dir: Optional[Path] = None,
    ) -> None:
        self.experiment_id = experiment_id

        if results_dir is None:
            # Default: experiments/results/<experiment_id>/
            project_root = Path(__file__).resolve().parent.parent
            results_dir = project_root / "experiments" / "results"

        self.run_dir = Path(results_dir) / experiment_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.events_path = self.run_dir / "events.jsonl"
        self._file = open(self.events_path, "a", encoding="utf-8")  # noqa: WPS515

        logger.info(
            f"ExperimentLogger initialised: experiment_id={experiment_id} "
            f"log={self.events_path}"
        )

    # -----------------------------------------------------------------------
    # Core write method
    # -----------------------------------------------------------------------

    def _write(self, event: Dict[str, Any]) -> None:
        """Write one JSON event to the JSONL file."""
        event.setdefault("experiment_id", self.experiment_id)
        event.setdefault("timestamp", _utcnow_iso())
        self._file.write(json.dumps(event, default=str) + "\n")
        self._file.flush()

    # -----------------------------------------------------------------------
    # Typed event methods
    # -----------------------------------------------------------------------

    def log_config(self, config: Dict[str, Any]) -> None:
        """Log the experiment configuration as the first event."""
        self._write({"event_type": "experiment_config", **config})
        # Also write a standalone config.json for easy inspection.
        config_path = self.run_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, default=str)

    def log_result(self, result: Dict[str, Any]) -> None:
        """Log a completed ExperimentResult."""
        self._write({"event_type": "task_result", **result})

    def log_escalation(
        self,
        task_id: str,
        attempt: int,
        reason: str,
        from_model: Optional[str] = None,
        to_model: Optional[str] = None,
        from_strategy: Optional[str] = None,
        to_strategy: Optional[str] = None,
        quality_score_before: Optional[float] = None,
    ) -> None:
        """Log an escalation event."""
        self._write({
            "event_type": "escalation",
            "task_id": task_id,
            "attempt": attempt,
            "reason": reason,
            "from_model": from_model,
            "to_model": to_model,
            "from_strategy": from_strategy,
            "to_strategy": to_strategy,
            "quality_score_before": quality_score_before,
        })

    def log_error(self, task_id: str, error_type: str, message: str) -> None:
        """Log a task-level error (does not stop the experiment)."""
        self._write({
            "event_type": "error",
            "task_id": task_id,
            "error_type": error_type,
            "message": message,
        })

    def log_experiment_start(self) -> None:
        """Mark the start of an experiment run."""
        self._write({"event_type": "experiment_start"})

    def log_experiment_end(self, total_tasks: int, successful_tasks: int) -> None:
        """Mark the end of an experiment run."""
        self._write({
            "event_type": "experiment_end",
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
        })

    def log_custom(self, event_type: str, **kwargs: Any) -> None:
        """Log a custom event type."""
        self._write({"event_type": event_type, **kwargs})

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def close(self) -> None:
        """Flush and close the log file."""
        if not self._file.closed:
            self._file.flush()
            self._file.close()
            logger.info(f"ExperimentLogger closed: {self.events_path}")

    def __enter__(self) -> "ExperimentLogger":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -----------------------------------------------------------------------
    # Read-back utilities
    # -----------------------------------------------------------------------

    def read_events(self) -> list:
        """Read all logged events from the JSONL file."""
        events = []
        if not self.events_path.exists():
            return events
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events
