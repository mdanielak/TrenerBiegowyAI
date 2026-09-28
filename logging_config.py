# -*- coding: utf-8 -*-
"""
Centralized logging configuration for Trener Biegowy AI.

Usage:
    from logging_config import setup_logging
    setup_logging()

Or for FastAPI:
    from logging_config import setup_logging
    setup_logging(level=logging.DEBUG)
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from config import PROJECT_ROOT


LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "trener.log"


def setup_logging(level=logging.INFO, log_file=None):
    """Configure logging with console + rotating file handler.

    Args:
        level: Minimum log level (default: INFO).
        log_file: Path to log file (default: logs/trener.log).
    """
    log_path = Path(log_file) if log_file else LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers to avoid duplicates on re-init
    root.handlers.clear()

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — INFO and above, concise
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(console)

    # File handler — DEBUG and above, rotating (5MB, keep 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.debug("Logging initialized: level=%s, file=%s", level, log_path)
