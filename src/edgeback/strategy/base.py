from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from edgeback.config.models import BaseStrictModel
from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderEvent, OrderIntent
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata

ParamsT = TypeVar("ParamsT", bound=BaseStrictModel)


class Strategy(ABC, Generic[ParamsT]):
    """
    Base class for all EdgeBack strategies.
    Strategies are pure logic modules and must not access the network,
    disk, or mutate engine state directly.
    """

    strategy_id: ClassVar[str]
    strategy_version: ClassVar[str]
    params_model: ClassVar[type[BaseStrictModel]]

    def __init__(self, params: ParamsT) -> None:
        self.params = params

    @classmethod
    @abstractmethod
    def metadata(cls) -> StrategyMetadata:
        """Return the strategy's metadata."""
        pass

    def initialize(self, ctx: StrategyContext) -> None:
        """Called once when the backtest starts."""
        pass

    def on_session_start(self, ctx: StrategyContext) -> None:
        """Called at the beginning of each trading session."""
        pass

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        """
        Called when a canonical bar is completed.
        Returns a list of order intents.
        """
        return []

    def on_order_update(self, ctx: StrategyContext, event: OrderEvent) -> None:
        """Called when an order state changes."""
        pass

    def on_session_end(self, ctx: StrategyContext) -> list[OrderIntent]:
        """Called at the end of each trading session."""
        return []

    def finalize(self, ctx: StrategyContext) -> None:
        """Called once when the backtest completes."""
        pass
