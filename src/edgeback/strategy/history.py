from datetime import datetime
from typing import Any

from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent
from edgeback.strategy.context import StrategyContext


class CausalStrategyContext(StrategyContext):
    """
    Concrete causal context provided to strategies.
    Ensures strategies cannot access future data or mutate engine state.
    """

    def __init__(self, engine_time_utc: datetime, bars_by_symbol: dict[str, list[Bar]]) -> None:
        """
        Initialize the context.

        Args:
            engine_time_utc: The current simulated time.
            bars_by_symbol: A dictionary mapping symbol to chronological list of all available Bars.
        """
        self._engine_time_utc = engine_time_utc
        self._bars = bars_by_symbol

    @property
    def engine_time_utc(self) -> datetime:
        return self._engine_time_utc

    def history(self, symbol: str, bars: int) -> list[Bar]:
        if bars <= 0:
            raise ValueError("bars must be greater than 0")

        if symbol not in self._bars:
            return []

        all_bars = self._bars[symbol]

        # Filter to only bars that have completed at or before engine_time_utc
        # We assume the lists are chronological
        causal_bars = []
        for b in reversed(all_bars):
            if b.bar_end_utc <= self._engine_time_utc:
                causal_bars.insert(0, b)
                if len(causal_bars) == bars:
                    break
        
        return causal_bars

    def create_intent(self, **kwargs: Any) -> OrderIntent:
        # Prevent strategies from bypassing causal boundaries on create_intent
        # e.g., if there's a constraint, but OrderIntent validation handles it
        return OrderIntent(**kwargs)
