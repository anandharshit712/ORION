"""
Structured logging configuration for ORION.

Provides JSON-formatted logging with simulation-context fields.
"""

import logging
import json
import sys
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON for structured log analysis."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include simulation context if attached
        if hasattr(record, "sim_time"):
            log_entry["sim_time"] = record.sim_time
        if hasattr(record, "scenario"):
            log_entry["scenario"] = record.scenario
        if hasattr(record, "seed"):
            log_entry["seed"] = record.seed
        # Include exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """
    Configure ORION logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, use JSON formatter; otherwise human-readable.
        log_file: Optional file path to write logs to.
    """
    root_logger = logging.getLogger("arep")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger under the arep namespace.

    Args:
        name: Logger name (will be prefixed with 'arep.').

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(f"arep.{name}")
