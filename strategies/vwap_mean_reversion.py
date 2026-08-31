"""Session VWAP mean-reversion hypothesis strategy."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator

from edgeback.domain import Bar, OrderIntent, Side
from edgeback.features import atr, vwap_series
from edgeback.strategy import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategyParameters,
    register_strategy,
)

_ET = ZoneInfo("America/New_York")


class VwapMeanReversionParams(StrategyParameters):
    earliest_entry_time: time = time(10, 0)
    latest_entry_time: time = time(15, 0)
    deviation_atr_multiple: float = Field(default=1.25, ge=0.25, le=5.0)
    atr_period: int = Field(default=14, ge=2, le=100)
    maximum_vwap_slope_bps_per_bar: float = Field(default=8.0, ge=0.0, le=100.0)
    stop_atr_multiple: float = Field(default=1.0, ge=0.1, le=5.0)
    target: str = "vwap"
    max_trades_per_symbol_session: int = Field(default=2, ge=1, le=10)

    @field_validator("earliest_entry_time", "latest_entry_time", mode="before")
    @classmethod
    def parse_time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @field_validator("target")
    @classmethod
    def target_value(cls, value: str) -> str:
        if value not in {"vwap", "partial_vwap"}:
            raise ValueError("target must be vwap or partial_vwap")
        return value


@register_strategy
class VwapMeanReversionStrategy(Strategy[VwapMeanReversionParams]):
    strategy_id = "vwap_mean_reversion"
    strategy_version = "0.1.0"
    params_model = VwapMeanReversionParams

    def __init__(self, params: VwapMeanReversionParams) -> None:
        super().__init__(params)
        self._session_date = None
        self._trades = 0

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Session VWAP Mean Reversion",
            description="Fade ATR-scaled deviations from causal session VWAP on low-slope regimes.",
            timeframes=("1m", "5m"),
            warmup_bars=30,
            previous_sessions_required=1,
            research_status="hypothesis",
            known_limitations=(
                "Provider volume coverage materially affects VWAP.",
                "The trend-regime proxy is intentionally simple.",
            ),
        )

    def on_session_start(self, ctx: StrategyContext) -> None:
        self._session_date = ctx.session_date
        self._trades = 0

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if self._session_date != bar.session_date:
            self.on_session_start(ctx)
        local = bar.bar_end_utc.astimezone(_ET).time().replace(tzinfo=None)
        if not self.params.earliest_entry_time <= local <= self.params.latest_entry_time:
            return []
        if self._trades >= self.params.max_trades_per_symbol_session:
            return []
        if ctx.position_quantity(bar.symbol) != 0:
            return []
        history = ctx.history(bar.symbol)
        session_bars = tuple(item for item in history if item.session_date == bar.session_date)
        vwaps = vwap_series(session_bars)
        if len(vwaps) < 2 or vwaps[-1] is None or vwaps[-2] is None:
            return []
        current_vwap = float(vwaps[-1])
        previous_vwap = float(vwaps[-2])
        slope_bps = abs(current_vwap / previous_vwap - 1.0) * 10_000.0
        if slope_bps > self.params.maximum_vwap_slope_bps_per_bar:
            return []
        atr_value = atr(history, self.params.atr_period)
        if atr_value is None or atr_value <= 0:
            return []
        deviation = (bar.close - current_vwap) / atr_value
        target = current_vwap if self.params.target == "vwap" else (bar.close + current_vwap) / 2.0
        features = {
            "session_vwap": current_vwap,
            "vwap_slope_bps_per_bar": slope_bps,
            "atr": atr_value,
            "deviation_atr": deviation,
        }
        if deviation <= -self.params.deviation_atr_multiple and target > bar.close:
            stop = bar.close - self.params.stop_atr_multiple * atr_value
            self._trades += 1
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.BUY,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="VWAP_LONG_REVERSION",
                    rationale="Price is ATR-scaled below a low-slope causal session VWAP.",
                    feature_snapshot=features,
                )
            ]
        if deviation >= self.params.deviation_atr_multiple and target < bar.close:
            stop = bar.close + self.params.stop_atr_multiple * atr_value
            self._trades += 1
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.SELL,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="VWAP_SHORT_REVERSION",
                    rationale="Price is ATR-scaled above a low-slope causal session VWAP.",
                    feature_snapshot=features,
                )
            ]
        return []
