import copy
from pathlib import Path
from typing import Any

import yaml

from edgeback.config.models import BacktestConfig
from edgeback.utils import ConfigurationError


def deep_update(base_dict: dict[str, Any], update_dict: dict[str, Any]) -> dict[str, Any]:
    """Recursively updates a dictionary."""
    result = copy.deepcopy(base_dict)
    for k, v in update_dict.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = deep_update(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Loads a YAML file using the safe loader."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigurationError(f"YAML file {path} did not produce a dictionary")
            return data
    except yaml.YAMLError as e:
        raise ConfigurationError(f"YAML parsing error in {path}: {e}")
    except FileNotFoundError:
        raise ConfigurationError(f"Configuration file not found: {path}")


def parse_cli_overrides(overrides: list[str]) -> dict[str, Any]:
    """
    Parses CLI overrides in the format key=value.
    Keys can be nested using dots: e.g., data.symbols=['AAPL'] or data.interval='1m'
    We will assume YAML syntax for values to allow list/number parsing.
    """
    result: dict[str, Any] = {}
    for override in overrides:
        if "=" not in override:
            raise ConfigurationError(f"Invalid override format (must be key=value): {override}")

        key, value_str = override.split("=", 1)
        key = key.strip()
        value_str = value_str.strip()

        try:
            value = yaml.safe_load(value_str)
        except yaml.YAMLError:
            # Fall back to string if parsing fails
            value = value_str

        parts = key.split(".")
        current = result
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = value
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
    return result


def resolve_config(
    yaml_path: str | Path,
    cli_overrides: list[str] | None = None,
    symbol_override: str | None = None,
) -> BacktestConfig:
    """
    Loads config from YAML and applies overrides.
    """
    data = load_yaml(yaml_path)

    if cli_overrides:
        overrides_dict = parse_cli_overrides(cli_overrides)
        data = deep_update(data, overrides_dict)

    if symbol_override:
        # CLI symbol override specifically requested.
        data = deep_update(data, {"data": {"symbols": [symbol_override]}})

    try:
        config = BacktestConfig.model_validate(data)
        return config
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")
