"""LoggingService — structured JSON logging through a port (no bare print).

Per Phase 3 (Observability Foundation): runtime services must log through a port,
not `print`, so logs are structured and ready for later Log Aggregation (Phase 5).
Uses ONLY stdlib + contracts (arch-gate LAW K8). No platform imports.
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per log line (who, what, when, level)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class LoggingService:
    """Owns a structured logger; services call .info/.warn/.error via it."""

    def __init__(
        self,
        name: str = "kroft.runtime",
        log_file: Optional[Path] = None,
        max_bytes: int = 1_000_000,
        backup_count: int = 3,
    ) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            stream = logging.StreamHandler(sys.stdout)
            stream.setFormatter(JsonFormatter())
            self._logger.addHandler(stream)
            if log_file is not None:
                try:
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    fh = RotatingFileHandler(
                        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
                    )
                    fh.setFormatter(JsonFormatter())
                    self._logger.addHandler(fh)
                except Exception:
                    pass

    def info(self, msg: str, **fields: Any) -> None:
        self._logger.info(self._fmt(msg, fields))

    def warn(self, msg: str, **fields: Any) -> None:
        self._logger.warning(self._fmt(msg, fields))

    def error(self, msg: str, **fields: Any) -> None:
        self._logger.error(self._fmt(msg, fields))

    def _fmt(self, msg: str, fields: dict) -> str:
        return msg + ("" if not fields else " " + json.dumps(fields, ensure_ascii=False))
