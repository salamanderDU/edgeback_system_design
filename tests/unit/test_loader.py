from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from edgeback.config.loader import load_yaml, parse_cli_overrides, resolve_config
from edgeback.utils import ConfigurationError


def test_load_yaml_safe_parsing() -> None:
    yaml_content = b"""
market:
  calendar: "XNYS"
"""
    with NamedTemporaryFile(delete=False) as f:
        f.write(yaml_content)
        f_path = f.name

    data = load_yaml(f_path)
    assert data["market"]["calendar"] == "XNYS"
    Path(f_path).unlink()


def test_load_yaml_unsafe_parsing_raises() -> None:
    yaml_content = b"""
foo: !!python/object/apply:os.system
  - echo "boom"
"""
    with NamedTemporaryFile(delete=False) as f:
        f.write(yaml_content)
        f_path = f.name

    with pytest.raises(ConfigurationError):
        load_yaml(f_path)
    Path(f_path).unlink()


def test_parse_cli_overrides() -> None:
    overrides = [
        "data.interval=1m",
        'data.symbols=["AAPL", "MSFT"]',
        "engine.initial_cash_usd=50000.0",
    ]
    parsed = parse_cli_overrides(overrides)
    assert parsed["data"]["interval"] == "1m"
    assert parsed["data"]["symbols"] == ["AAPL", "MSFT"]
    assert parsed["engine"]["initial_cash_usd"] == 50000.0


def test_resolve_config() -> None:
    config = resolve_config(
        yaml_path="configs/example_backtest.yaml",
        cli_overrides=["engine.initial_cash_usd=777.0"],
        symbol_override="TSLA",
    )

    assert config.engine.initial_cash_usd == 777.0
    assert config.data.symbols == ["TSLA"]
