from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from edgeback.domain import (
    Bar,
    IntentType,
    OrderIntent,
    OrderType,
    PortfolioSnapshot,
    Side,
)


class StrategyContext:
    """Read-only causal view. Histories are copied and clipped at engine time."""

    __slots__ = (
        "_current_bar",
        "_engine_time_utc",
        "_history",
        "_intent_id_factory",
        "_portfolio",
        "_session_date",
        "_strategy_id",
        "_strategy_version",
    )

    def __init__(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        engine_time_utc: datetime,
        session_date: date,
        current_bar: Bar | None,
        histories: dict[str, tuple[Bar, ...]],
        portfolio: PortfolioSnapshot,
        intent_id_factory: Callable[[], int],
    ) -> None:
        self._strategy_id = strategy_id
        self._strategy_version = strategy_version
        self._engine_time_utc = engine_time_utc
        self._session_date = session_date
        self._current_bar = current_bar
        self._portfolio = portfolio
        self._intent_id_factory = intent_id_factory
        self._history = {
            symbol: tuple(bar for bar in bars if bar.bar_end_utc <= engine_time_utc)
            for symbol, bars in histories.items()
        }

    @property
    def engine_time_utc(self) -> datetime:
        return self._engine_time_utc

    @property
    def session_date(self) -> date:
        return self._session_date

    @property
    def current_bar(self) -> Bar | None:
        return self._current_bar

    @property
    def portfolio(self) -> PortfolioSnapshot:
        return self._portfolio

    def history(
        self,
        symbol: str,
        *,
        bars: int | None = None,
        include_current: bool = True,
    ) -> tuple[Bar, ...]:
        symbol = symbol.strip().upper()
        available = self._history.get(symbol, ())
        if not include_current and self._current_bar is not None and self._current_bar.symbol == symbol:
            available = tuple(bar for bar in available if bar.bar_end_utc < self._current_bar.bar_end_utc)
        if bars is not None:
            if bars < 0:
                raise ValueError("bars must be nonnegative")
            available = available[-bars:] if bars else ()
        return tuple(available)

    def position_quantity(self, symbol: str) -> int:
        symbol = symbol.strip().upper()
        for position in self._portfolio.positions:
            if position.symbol == symbol:
                return position.quantity
        return 0

    def create_intent(
        self,
        *,
        symbol: str,
        side: Side,
        reason_code: str,
        rationale: str,
        intent_type: IntentType = IntentType.ENTRY,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_trigger_price: float | None = None,
        requested_quantity: int | None = None,
        sizing_model: str | None = None,
        entry_reference_price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        priority: int = 0,
        feature_snapshot: dict[str, Any] | None = None,
        protective_exit: bool = False,
    ) -> OrderIntent:
        return OrderIntent(
            intent_id=self._intent_id_factory(),
            strategy_id=self._strategy_id,
            strategy_version=self._strategy_version,
            symbol=symbol,
            side=side,
            intent_type=intent_type,
            order_type=order_type,
            signal_time_utc=self._engine_time_utc,
            limit_price=limit_price,
            stop_trigger_price=stop_trigger_price,
            requested_quantity=requested_quantity,
            sizing_model=sizing_model,
            entry_reference_price=entry_reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            priority=priority,
            reason_code=reason_code,
            rationale=rationale,
            feature_snapshot=feature_snapshot or {},
            protective_exit=protective_exit,
        )
