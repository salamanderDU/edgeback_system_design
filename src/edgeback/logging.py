"""Structured JSONL logging with secret redaction."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edgeback.utils import redact


class JsonlLogger:
    def __init__(self, path: Path, *, run_id: str | None = None) -> None:
        self.path = path
        self.run_id = run_id
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        level: str,
        component: str,
        event: str,
        *,
        symbol: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "level": level.upper(),
            "component": component,
            "run_id": self.run_id,
            "event": event,
            "symbol": symbol,
            "context": redact(context or {}),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    def info(self, component: str, event: str, **kwargs: Any) -> None:
        self.emit("INFO", component, event, **kwargs)

    def warning(self, component: str, event: str, **kwargs: Any) -> None:
        self.emit("WARNING", component, event, **kwargs)

    def error(self, component: str, event: str, **kwargs: Any) -> None:
        self.emit("ERROR", component, event, **kwargs)


logger = logging.getLogger("edgeback")
