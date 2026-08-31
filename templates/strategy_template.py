"""Copy to strategies/<strategy_id>.py, then add the trusted module to the registry."""

from __future__ import annotations

from edgeback.domain import Bar, OrderIntent
from edgeback.strategy import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategyParameters,
    register_strategy,
)


class ExampleParams(StrategyParameters):
    warmup_bars: int = 20


@register_strategy
class ExampleStrategy(Strategy[ExampleParams]):
    strategy_id = "example_strategy"
    strategy_version = "0.1.0"
    params_model = ExampleParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Example Strategy",
            description="Replace with a falsifiable causal hypothesis.",
            markets=("US_EQUITY", "US_ETF"),
            timeframes=("5m",),
            directions=("long", "short"),
            required_fields=("open", "high", "low", "close", "volume"),
            warmup_bars=20,
            research_status="hypothesis",
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        history = ctx.history(bar.symbol, bars=self.params.warmup_bars)
        if len(history) < self.params.warmup_bars:
            return []
        return []
