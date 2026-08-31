"""Safe YAML loading and deterministic CLI override resolution."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from edgeback.config.models import ResearchConfig, ResolutionMetadata, ResolvedConfig
from edgeback.errors import ConfigurationError


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Could not load YAML config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Config root must be a mapping: {path}")
    return raw


def parse_typed_value(raw: str) -> Any:
    """Parse a single YAML scalar/collection without allowing object tags."""
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid override value {raw!r}: {exc}") from exc
    allowed = (str, int, float, bool, list, dict, type(None))
    if not isinstance(value, allowed):
        raise ConfigurationError(f"Unsupported override value type: {type(value).__name__}")
    return value


def _apply_path(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    if not parts or any(not part for part in parts):
        raise ConfigurationError(f"Invalid override path: {dotted_path!r}")
    cursor: dict[str, Any] = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if child is None:
            child = {}
            cursor[part] = child
        if not isinstance(child, dict):
            raise ConfigurationError(f"Override path crosses non-mapping field: {dotted_path}")
        cursor = child
    cursor[parts[-1]] = value


def resolve_config(
    path: str | Path,
    *,
    symbols: list[str] | tuple[str, ...] | None = None,
    params: list[str] | tuple[str, ...] = (),
    sets: list[str] | tuple[str, ...] = (),
    now: datetime | None = None,
) -> ResolvedConfig:
    config_path = Path(path).resolve()
    payload = copy.deepcopy(_load_yaml_mapping(config_path))
    sources: list[str] = [f"yaml:{config_path}"]

    if symbols:
        payload.setdefault("data", {})["symbols"] = list(symbols)
        sources.append("cli:symbol")

    for item in params:
        if "=" not in item:
            raise ConfigurationError(f"Strategy parameter override must be name=value: {item!r}")
        name, raw_value = item.split("=", 1)
        payload.setdefault("strategy", {}).setdefault("params", {})[name] = parse_typed_value(
            raw_value
        )
        sources.append(f"cli:param:{name}")

    for item in sets:
        if "=" not in item:
            raise ConfigurationError(f"Override must be path=value: {item!r}")
        dotted_path, raw_value = item.split("=", 1)
        _apply_path(payload, dotted_path, parse_typed_value(raw_value))
        sources.append(f"cli:set:{dotted_path}")

    moment = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        provisional = ResolvedConfig.model_validate(payload)
        resolved_range = provisional.data.date_range.resolve(today=moment.date())
        payload.setdefault("data", {})["date_range"] = resolved_range.model_dump(mode="json")
        payload["resolution"] = ResolutionMetadata(
            resolved_at_utc=moment,
            config_path=config_path,
            override_sources=tuple(sources),
        ).model_dump(mode="python")
        return ResolvedConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid EdgeBack config {config_path}:\n{exc}") from exc


def load_research_config(path: str | Path) -> ResearchConfig:
    config_path = Path(path).resolve()
    try:
        return ResearchConfig.model_validate(_load_yaml_mapping(config_path))
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid research config {config_path}:\n{exc}") from exc
