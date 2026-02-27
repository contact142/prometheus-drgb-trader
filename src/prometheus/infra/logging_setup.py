"""Structured logging with rotation."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any


def setup_logging(config: dict[str, Any] | None = None) -> None:
    """Configure structured logging with file rotation and console output.

    Args:
        config: Logging config dict with keys:
            level, file, max_bytes, backup_count.
    """
    config = config or {}
    level = getattr(logging, config.get("level", "INFO").upper(), logging.INFO)
    log_file = config.get("file", "logs/prometheus.log")
    max_bytes = config.get("max_bytes", 10_000_000)
    backup_count = config.get("backup_count", 5)

    # Ensure log directory exists
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("prometheus").setLevel(level)
