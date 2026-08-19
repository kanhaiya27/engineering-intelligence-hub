"""
Engineering Intelligence Hub — Structured Logging
==================================================
Wraps loguru with project-specific configuration:
  - Human-readable console output in development
  - Structured JSON sink for experiment/audit trails
  - Correlation ID support for tracing requests

Usage
-----
    from core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Processing task", task_id="abc-123")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger as _loguru_logger

# Re-export so callers do `from core.logging import logger` if preferred.
logger = _loguru_logger

# Internal flag to prevent double-initialisation.
_configured = False


def configure_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    json_logs: bool = False,
    experiment_log_path: Optional[Path] = None,
) -> None:
    """
    Configure loguru handlers for the application.

    Parameters
    ----------
    log_level:
        Minimum log level for all handlers (DEBUG, INFO, WARNING, ERROR).
    log_dir:
        If provided, a rotating file log is written to this directory.
    json_logs:
        If True, the console sink emits JSON-serialised log records
        (useful when running in containerised environments).
    experiment_log_path:
        If provided, a separate JSONL sink is created for experiment-level
        structured records (allows easy pandas/DuckDB querying later).
    """
    global _configured

    # Remove default loguru handler.
    _loguru_logger.remove()

    # --- Console sink ---
    if json_logs:
        _loguru_logger.add(
            sys.stdout,
            level=log_level,
            serialize=True,
        )
    else:
        _loguru_logger.add(
            sys.stdout,
            level=log_level,
            colorize=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
        )

    # --- Rotating file sink (optional) ---
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        _loguru_logger.add(
            log_dir / "eih_{time:YYYY-MM-DD}.log",
            level=log_level,
            rotation="00:00",   # Rotate at midnight
            retention="30 days",
            compression="gz",
            serialize=False,
        )

    # --- Experiment JSONL sink (optional) ---
    if experiment_log_path is not None:
        experiment_log_path = Path(experiment_log_path)
        experiment_log_path.parent.mkdir(parents=True, exist_ok=True)
        _loguru_logger.add(
            str(experiment_log_path),
            level="DEBUG",
            serialize=True,
            filter=lambda record: "experiment" in record["extra"],
        )

    _configured = True


def get_logger(name: str) -> "logger.__class__":
    """
    Return a loguru logger bound with the given name.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.
    """
    if not _configured:
        # Provide a sensible default if configure_logging was never called.
        configure_logging()
    return _loguru_logger.bind(module=name)
