"""Logging utilities for the traffic monitoring algorithm service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

_LOG_LEVEL = os.getenv("ALGO_LOG_LEVEL", "INFO")
_LOG_DIR = Path(os.getenv("ALGO_LOG_DIR", "logs"))


def configure_logging() -> None:
    """Configure loguru sinks for console (and optional file)."""
    logger.remove()
    logger.add(sys.stdout, level=_LOG_LEVEL, backtrace=False, diagnose=False)

    if os.getenv("ALGO_LOG_TO_FILE", "false").lower() in {"1", "true", "yes"}:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            _LOG_DIR / "algo-service.log",
            level=_LOG_LEVEL,
            rotation="10 MB",
            retention="7 days",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
