from typing import Any

from edgeback.strategy.base import Strategy


class StrategyRegistryError(Exception):
    pass


_REGISTRY: dict[str, type[Strategy[Any]]] = {}


def register_strategy(strategy_cls: type[Strategy[Any]]) -> type[Strategy[Any]]:
    """
    Decorator to register a strategy class in the global trusted registry.
    """
    if not issubclass(strategy_cls, Strategy):
        raise StrategyRegistryError(f"{strategy_cls.__name__} must inherit from Strategy")

    strategy_id = getattr(strategy_cls, "strategy_id", None)
    if not strategy_id:
        raise StrategyRegistryError(f"{strategy_cls.__name__} must define a strategy_id")

    if strategy_id in _REGISTRY:
        raise StrategyRegistryError(f"Strategy {strategy_id} is already registered")

    _REGISTRY[strategy_id] = strategy_cls
    return strategy_cls


def get_strategy_class(strategy_id: str) -> type[Strategy[Any]]:
    """
    Retrieve a strategy class by its ID.
    Raises StrategyRegistryError if not found.
    """
    if strategy_id not in _REGISTRY:
        raise StrategyRegistryError(f"Strategy {strategy_id} not found in registry")
    return _REGISTRY[strategy_id]


def list_strategies() -> list[type[Strategy[Any]]]:
    """
    Return a list of all registered strategy classes.
    """
    return list(_REGISTRY.values())


def clear_registry() -> None:
    """
    Clear the registry (useful for testing).
    """
    _REGISTRY.clear()
