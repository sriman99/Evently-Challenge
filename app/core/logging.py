"""
Logging configuration
"""

import logging
import logging.config
import json
from datetime import datetime
from typing import Dict, Any

from app.config import settings


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)


def setup_logging():
    """
    Configure application logging
    """
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "json": {
                "()": JSONFormatter
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "json" if settings.LOG_FORMAT == "json" else "default",
                "stream": "ext://sys.stdout"
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "json",
                "filename": "logs/app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5
            }
        },
        "loggers": {
            "app": {
                "level": settings.LOG_LEVEL,
                "handlers": ["console", "file"] if not settings.is_testing else ["console"],
                "propagate": False
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            }
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console"]
        }
    }

    # Create logs directory if it doesn't exist
    import os
    os.makedirs("logs", exist_ok=True)

    logging.config.dictConfig(log_config)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Custom logger adapter for adding context
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        # Add request context if available
        if hasattr(self, "request_id"):
            kwargs["extra"]["request_id"] = self.request_id

        if hasattr(self, "user_id"):
            kwargs["extra"]["user_id"] = self.user_id

        return msg, kwargs