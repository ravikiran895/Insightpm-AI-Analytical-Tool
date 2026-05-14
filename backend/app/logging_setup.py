"""
Logging setup with file rotation.

Logs go to ~/.insightpm/logs/insightpm.log. Rotation: 5 MB per file, keep
last 5. Console output at INFO level for dev visibility; file at DEBUG.

Why this matters: when something breaks at 11pm and you're not at the
terminal, you have no trail. With this, you get the last few hours of
operation reconstructable from the log file.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)-25s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> Path:
    """Configure rotating file logger + console logger.
    Idempotent: safe to call multiple times.

    Returns: the log file path so other code can reference it (e.g. for
    a /api/diagnostics endpoint later)."""
    log_dir = Path.home() / ".insightpm" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "insightpm.log"

    root = logging.getLogger()
    # If already configured (e.g. uvicorn --reload re-imports), don't duplicate handlers.
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return log_file

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    # Rotating file: 5 MB per file, keep 5 backups (~25 MB total max).
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    # Only add console handler if we're not running under uvicorn (it has its own).
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(console_handler)

    # Tame noisy libraries
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    log = logging.getLogger("insightpm")
    log.info(f"Logging initialized -> {log_file}")
    return log_file


def get_log_path() -> Path:
    return Path.home() / ".insightpm" / "logs" / "insightpm.log"
