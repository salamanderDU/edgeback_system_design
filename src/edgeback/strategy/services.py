import importlib
import pkgutil
from typing import Any

from edgeback.strategy.base import Strategy
from edgeback.strategy.models import StrategyDetail, StrategySummary
from edgeback.strategy.registry import (
    StrategyRegistryError,
    get_strategy_class,
    list_strategies,
    register_strategy,
)


def discover_strategies(package_name: str = "strategies") -> list[type[Strategy[Any]]]:
    """
    Discovers and imports all strategy modules from the trusted strategies package.
    """
    try:
        pkg = importlib.import_module(package_name)
    except ImportError as err:
        msg = f"Could not import strategies package '{package_name}': {err}"
        raise StrategyRegistryError(msg) from err

    if hasattr(pkg, "__path__"):
        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            if not module_name.startswith("_"):
                full_module_name = f"{package_name}.{module_name}"
                mod = importlib.import_module(full_module_name)
                # Register any Strategy subclasses in the module that might not be registered yet
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Strategy)
                        and attr is not Strategy
                        and getattr(attr, "strategy_id", None)
                    ):
                        strat_id = attr.strategy_id
                        try:
                            existing = get_strategy_class(strat_id)
                            if existing is not attr:
                                err_msg = (
                                    f"Strategy ID conflict: {strat_id} is implemented by "
                                    f"multiple classes ({existing.__name__} and {attr.__name__})"
                                )
                                raise StrategyRegistryError(err_msg)
                        except StrategyRegistryError as err:
                            if "not found in registry" in str(err):
                                register_strategy(attr)
                            else:
                                raise

    return list_strategies()


def list_strategies_service() -> list[StrategySummary]:
    """
    Returns a deterministically sorted list of summaries for all registered strategies.
    """
    discover_strategies()
    strategies_list = list_strategies()

    summaries = []
    for strat_cls in strategies_list:
        meta = strat_cls.metadata()
        summaries.append(
            StrategySummary(
                strategy_id=meta.strategy_id,
                version=meta.version,
                name=meta.name or meta.strategy_id,
                description=meta.description,
                scope=meta.scope,
                research_status=meta.research_status,
                warmup_bars=meta.warmup_bars,
            )
        )

    return sorted(summaries, key=lambda s: s.strategy_id)


def describe_strategy_service(strategy_id: str) -> StrategyDetail:
    """
    Returns complete metadata and parameter schema for a given strategy ID.
    Raises StrategyRegistryError if the strategy is not found.
    """
    discover_strategies()
    strat_cls = get_strategy_class(strategy_id)

    meta = strat_cls.metadata()
    params_schema = strat_cls.params_model.model_json_schema()

    default_params: dict[str, Any] = {}
    for name, field in strat_cls.params_model.model_fields.items():
        if field.default is not None and field.default is not ...:
            default_params[name] = field.default

    return StrategyDetail(
        strategy_id=strat_cls.strategy_id,
        version=strat_cls.strategy_version,
        metadata=meta,
        params_schema=params_schema,
        default_params=default_params,
    )
