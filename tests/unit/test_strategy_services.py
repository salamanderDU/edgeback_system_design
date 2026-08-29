import pytest

from edgeback.config.models import BaseStrictModel
from edgeback.strategy.base import Strategy
from edgeback.strategy.models import StrategyMetadata
from edgeback.strategy.registry import (
    StrategyRegistryError,
    register_strategy,
)
from edgeback.strategy.services import (
    describe_strategy_service,
    list_strategies_service,
)


def test_list_strategies_service() -> None:
    summaries = list_strategies_service()
    assert len(summaries) >= 1

    orb = next((s for s in summaries if s.strategy_id == "opening_range_breakout"), None)
    assert orb is not None
    assert orb.version == "0.1.0"
    assert orb.name == "Opening Range Breakout"
    assert orb.scope == "per_symbol"
    assert orb.warmup_bars == 20
    assert orb.research_status == "hypothesis"

    # Deterministic sorting check
    ids = [s.strategy_id for s in summaries]
    assert ids == sorted(ids)


def test_describe_strategy_service() -> None:
    detail = describe_strategy_service("opening_range_breakout")
    assert detail.strategy_id == "opening_range_breakout"
    assert detail.version == "0.1.0"
    assert detail.metadata.name == "Opening Range Breakout"

    # Check params schema
    assert "properties" in detail.params_schema
    assert "opening_range_minutes" in detail.params_schema["properties"]
    assert "breakout_buffer_bps" in detail.params_schema["properties"]

    # Check default params
    assert detail.default_params.get("opening_range_minutes") == 15
    assert detail.default_params.get("directions") == "both"
    assert detail.default_params.get("reward_risk") == 1.50


def test_describe_strategy_not_found() -> None:
    with pytest.raises(StrategyRegistryError, match="not found in registry"):
        describe_strategy_service("nonexistent_strategy_xyz")


def test_duplicate_strategy_id_conflict() -> None:
    class DummyParams(BaseStrictModel):
        val: int = 1

    class DummyStrategy1(Strategy[DummyParams]):
        strategy_id = "test_duplicate_id"
        strategy_version = "0.1.0"
        params_model = DummyParams

        @classmethod
        def metadata(cls) -> StrategyMetadata:
            return StrategyMetadata(strategy_id=cls.strategy_id, version=cls.strategy_version)

    class DummyStrategy2(Strategy[DummyParams]):
        strategy_id = "test_duplicate_id"
        strategy_version = "0.2.0"
        params_model = DummyParams

        @classmethod
        def metadata(cls) -> StrategyMetadata:
            return StrategyMetadata(strategy_id=cls.strategy_id, version=cls.strategy_version)

    register_strategy(DummyStrategy1)

    with pytest.raises(StrategyRegistryError, match="already registered"):
        register_strategy(DummyStrategy2)
