from datetime import datetime, timezone
from typing import Any

import pytest

from edgeback.config.models import BaseStrictModel
from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent
from edgeback.strategy import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategyRegistryError,
    clear_registry,
    get_strategy_class,
    list_strategies,
    register_strategy,
)


class DummyParams(BaseStrictModel):
    threshold: float


class DummyStrategy(Strategy[DummyParams]):
    strategy_id = "dummy"
    strategy_version = "1.0.0"
    params_model = DummyParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Dummy",
            description="Dummy strat",
            scope="per_symbol",
            warmup_bars=10,
            required_fields=("close",),
            research_status="hypothesis",
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        return []


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    clear_registry()


def test_strategy_metadata() -> None:
    meta = DummyStrategy.metadata()
    assert meta.strategy_id == "dummy"
    assert meta.version == "1.0.0"
    assert meta.warmup_bars == 10
    assert meta.research_status == "hypothesis"


def test_strategy_instantiation() -> None:
    params = DummyParams(threshold=1.5)
    strat = DummyStrategy(params)
    assert strat.params.threshold == 1.5


def test_register_strategy() -> None:
    register_strategy(DummyStrategy)
    cls = get_strategy_class("dummy")
    assert cls is DummyStrategy

    strats = list_strategies()
    assert len(strats) == 1
    assert strats[0] is DummyStrategy


def test_register_strategy_duplicate_fails() -> None:
    register_strategy(DummyStrategy)
    with pytest.raises(StrategyRegistryError, match="already registered"):
        register_strategy(DummyStrategy)


def test_get_strategy_missing_fails() -> None:
    with pytest.raises(StrategyRegistryError, match="not found"):
        get_strategy_class("unknown")


def test_register_invalid_class_fails() -> None:
    class NotAStrategy:
        pass

    with pytest.raises(StrategyRegistryError, match="must inherit from Strategy"):
        register_strategy(NotAStrategy)  # type: ignore


def test_register_missing_id_fails() -> None:
    class MissingIdStrategy(Strategy[DummyParams]):
        strategy_version = "1.0.0"
        params_model = DummyParams

        @classmethod
        def metadata(cls) -> StrategyMetadata:
            return StrategyMetadata(
                strategy_id="missing",
                version=cls.strategy_version,
            )

    with pytest.raises(StrategyRegistryError, match="must define a strategy_id"):
        register_strategy(MissingIdStrategy)
