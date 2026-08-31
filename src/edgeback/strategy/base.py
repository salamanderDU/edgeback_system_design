from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from edgeback.domain import Bar, OrderEvent, OrderIntent
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata, StrategyParameters

ParamsT = TypeVar("ParamsT", bound=StrategyParameters)


class Strategy(ABC, Generic[ParamsT]):
    strategy_id: ClassVar[str]
    strategy_version: ClassVar[str]
    params_model: ClassVar[type[ParamsT]]

    def __init__(self, params: ParamsT) -> None:
        self.params = params

    @classmethod
    @abstractmethod
    def metadata(cls) -> StrategyMetadata: ...

    def initialize(self, ctx: StrategyContext) -> None:
        del ctx

    def on_session_start(self, ctx: StrategyContext) -> None:
        del ctx

    @abstractmethod
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]: ...

    def on_order_update(self, ctx: StrategyContext, event: OrderEvent) -> None:
        del ctx, event

    def on_session_end(self, ctx: StrategyContext) -> list[OrderIntent]:
        del ctx
        return []

    def finalize(self, ctx: StrategyContext) -> None:
        del ctx

    def serializable_state(self) -> dict[str, object]:
        return {
            key: value
            for key, value in vars(self).items()
            if key != "params" and isinstance(value, (str, int, float, bool, list, tuple, dict, type(None)))
        }
