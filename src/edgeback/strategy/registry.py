from __future__ import annotations

import importlib
from typing import Any, TypeVar

from edgeback.errors import StrategyError
from edgeback.strategy.base import Strategy

StrategyType = TypeVar("StrategyType", bound=type[Strategy[Any]])
_REGISTRY: dict[str, type[Strategy[Any]]] = {}
_BUILTINS_LOADED = False


def register_strategy(cls: StrategyType) -> StrategyType:
    existing = _REGISTRY.get(cls.strategy_id)
    if existing is not None and existing is not cls:
        raise StrategyError(f"Duplicate strategy id: {cls.strategy_id}")
    _REGISTRY[cls.strategy_id] = cls
    return cls


def load_builtin_strategies() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    for module in (
        "strategies.opening_range_breakout",
        "strategies.vwap_mean_reversion",
        "strategies.gap_momentum",
    ):
        importlib.import_module(module)
    _BUILTINS_LOADED = True


def strategy_classes() -> tuple[type[Strategy[Any]], ...]:
    load_builtin_strategies()
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def get_strategy_class(strategy_id: str) -> type[Strategy[Any]]:
    load_builtin_strategies()
    try:
        return _REGISTRY[strategy_id]
    except KeyError as exc:
        raise StrategyError(f"Unknown trusted strategy: {strategy_id}") from exc


def create_strategy(
    strategy_id: str, params: dict[str, Any], expected_version: str | None = None
) -> Strategy[Any]:
    cls = get_strategy_class(strategy_id)
    if expected_version is not None and cls.strategy_version != expected_version:
        raise StrategyError(
            f"Strategy version mismatch for {strategy_id}: expected {expected_version}, "
            f"installed {cls.strategy_version}"
        )
    try:
        parsed = cls.params_model.model_validate(params)
    except Exception as exc:
        raise StrategyError(f"Invalid parameters for {strategy_id}: {exc}") from exc
    return cls(parsed)


def clear_registry_for_tests() -> None:
    global _BUILTINS_LOADED
    _REGISTRY.clear()
    _BUILTINS_LOADED = False
