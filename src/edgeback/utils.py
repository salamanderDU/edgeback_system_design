"""Small deterministic utilities used across EdgeBack."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"(secret|token|password|api[_-]?key)", re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(UTC)


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, Path)):
        return value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot JSON serialize {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=json_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def stable_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: Any) -> Any:
    """Recursively redact values whose keys look secret-bearing."""
    if isinstance(value, Mapping):
        return {
            str(key): "***REDACTED***" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".edgeback_write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


def package_versions(names: tuple[str, ...]) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def env_present(name: str) -> bool:
    return bool(os.getenv(name))
