from __future__ import annotations

from pathlib import Path

from edgeback.logging import JsonlLogger
from edgeback.utils import redact


def test_recursive_secret_redaction_and_jsonl(tmp_path: Path) -> None:
    value = {
        "api_key": "top-secret",
        "nested": {"password": "also-secret", "safe": 7},
        "items": [{"token": "third-secret"}],
    }
    cleaned = redact(value)
    assert "top-secret" not in repr(cleaned)
    assert cleaned["nested"]["safe"] == 7
    target = tmp_path / "log.jsonl"
    JsonlLogger(target).info("test", "SECRET_CHECK", context=value)
    text = target.read_text()
    assert "top-secret" not in text
    assert "also-secret" not in text
    assert "third-secret" not in text
