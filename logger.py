"""
Loguru-based logging setup for crypto-monitor.

Call ``setup_logging()`` once at application startup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from config import LogSettings


def setup_logging(log_settings: LogSettings | None = None) -> None:
    """Configure loguru sinks based on LogSettings.

    Parameters
    ----------
    log_settings:
        If *None*, a fresh ``LogSettings()`` is created (reads from env / .env).
    """
    if log_settings is None:
        log_settings = LogSettings()

    # Remove default loguru handler so we control everything
    logger.remove()

    # ── File sink (rotation by size) ──────────────────────────────────────
    log_path = Path(log_settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        rotation=log_settings.log_max_bytes,
        retention="7 days",
        encoding="utf-8",
        enqueue=True,           # thread-safe
        backtrace=True,
        diagnose=False,         # keep prod logs clean
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
            "{name}:{function}:{line} - {message}"
        ),
    )

    # ── Stdout sink (optional) ────────────────────────────────────────────
    if log_settings.log_to_stdout:
        logger.add(
            sys.stdout,
            level="DEBUG",
            enqueue=True,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | "
                "<level>{level:<8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
                "- <level>{message}</level>"
            ),
        )

    logger.info("Logging initialised  file={}", log_settings.log_file)
