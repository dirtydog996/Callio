"""Centralized logging configuration for Callio.

Environment variables:
  CALLIO_LOG_LEVEL   – root log level (default: INFO).
  CALLIO_LOG_FILE    – optional log file path; if set, logs are written there as well.
  CALLIO_LOG_FORMAT  – optional format override.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional


_DEFAULT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    fmt: Optional[str] = None,
) -> None:
    """Configure the root logger once. Subsequent calls are no-ops."""
    global _configured
    if _configured:
        return
    _configured = True

    _level = (level or os.getenv("CALLIO_LOG_LEVEL", "INFO")).upper()
    _fmt = fmt or os.getenv("CALLIO_LOG_FORMAT", _DEFAULT_FORMAT)
    _file = log_file or os.getenv("CALLIO_LOG_FILE", "")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if _file:
        handlers.append(logging.FileHandler(_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, _level, logging.INFO),
        format=_fmt,
        datefmt=_DATE_FORMAT,
        handlers=handlers,
        force=True,
    )

    for noisy in ("httpx", "httpcore", "uvicorn.access", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
