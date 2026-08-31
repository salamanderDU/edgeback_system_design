from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from edgeback.config.hashing import config_hash
from edgeback.config.loader import parse_typed_value, resolve_config
from edgeback.config.models import DateRangeConfig, ResolvedConfig
from edgeback.errors import ConfigurationError


ROOT = Path(__file__).parents[2]


def test_example_config_resolves_rolling_range_and_normalizes_symbols() -> None:
    config = resolve_config(
        ROOT / "configs/example_backtest.yaml",
        symbols=[" aapl ", "MSFT", "aapl"],
        params=["opening_range_minutes=30", "reward_risk=2.0"],
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    assert config.data.symbols == ("AAPL", "MSFT")
    assert config.data.date_range.mode == "explicit"
    assert config.data.date_range.end.isoformat() == "2026-08-31"
    assert config.strategy.params["opening_range_minutes"] == 30
    assert config.strategy.params["reward_risk"] == 2.0


def test_unknown_config_key_is_rejected() -> None:
    payload = resolve_config(ROOT / "configs/example_backtest.yaml").model_dump(mode="python")
    payload.pop("resolution", None)
    payload["engine"]["future_magic"] = True
    with pytest.raises(ValidationError):
        ResolvedConfig.model_validate(payload)


def test_date_range_modes_are_exclusive() -> None:
    with pytest.raises(ValidationError):
        DateRangeConfig(mode="explicit", start=None, end=None)
    with pytest.raises(ValidationError):
        DateRangeConfig(mode="rolling", start="2025-01-01", lookback_calendar_days=10)


def test_unsafe_yaml_tag_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("!!python/object/apply:os.system ['echo nope']", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        resolve_config(config_path)


def test_typed_override_never_executes_python() -> None:
    assert parse_typed_value("[1, 2]") == [1, 2]
    with pytest.raises(ConfigurationError):
        parse_typed_value("!!python/object/apply:os.system ['echo nope']")


def test_config_hash_ignores_resolution_timestamp() -> None:
    first = resolve_config(
        ROOT / "configs/example_backtest.yaml", now=datetime(2026, 8, 30, tzinfo=UTC)
    )
    second = resolve_config(
        ROOT / "configs/example_backtest.yaml", now=datetime(2026, 8, 31, tzinfo=UTC)
    )
    # Rolling ranges legitimately resolve differently, so use an explicit copy for the identity assertion.
    payload = first.model_dump(mode="python", exclude={"resolution"})
    first_explicit = ResolvedConfig.model_validate(payload)
    second_explicit = ResolvedConfig.model_validate(
        {**payload, "resolution": second.resolution.model_dump(mode="python")}
    )
    assert config_hash(first_explicit) == config_hash(second_explicit)
