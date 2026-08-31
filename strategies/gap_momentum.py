"""Gap-direction momentum hypothesis strategy."""

from __future__ import annotations

from datetime import time, timedelta
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from edgeback.domain import Bar, OrderIntent, Side
from edgeback.features import atr, median_volume_ratio
from edgeback.strategy import (
    Strategy,
    StrategyContext,
    StrategyMetadata,
    StrategyParameters,
    register_strategy,
)

_ET = ZoneInfo("America/New_York")


class GapMomentumParams(StrategyParameters):
    minimum_gap_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    maximum_gap_pct: float = Field(default=8.0, ge=0.5, le=50.0)
    confirmation_minutes: int = Field(default=15, ge=5, le=60)
    confirmation_breakout_buffer_bps: float = Field(default=5.0, ge=0.0, le=100.0)
    minimum_volume_ratio: float = Field(default=1.2, ge=0.0, le=10.0)
    stop_atr_multiple: float = Field(default=1.0, ge=0.1, le=5.0)
    reward_risk: float = Field(default=1.5, ge=0.25, le=10.0)
    latest_entry_time: time = time(11, 30)

    @field_validator("latest_entry_time", mode="before")
    @classmethod
    def parse_time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def gap_bounds(self) -> "GapMomentumParams":
        if self.minimum_gap_pct > self.maximum_gap_pct:
            raise ValueError("minimum_gap_pct cannot exceed maximum_gap_pct")
        return self


@register_strategy
class GapMomentumStrategy(Strategy[GapMomentumParams]):
    strategy_id = "gap_momentum"
    strategy_version = "0.1.0"
    params_model = GapMomentumParams

    def __init__(self, params: GapMomentumParams) -> None:
        super().__init__(params)
        self._session_date = None
        self._session_open_utc = None
        self._gap_pct: float | None = None
        self._direction: str | None = None
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._traded = False

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Gap Direction Momentum",
            description="Trade early confirmation in the direction of a bounded overnight gap.",
            timeframes=("1m", "5m", "15m"),
            warmup_bars=20,
            previous_sessions_required=2,
            research_status="hypothesis",
            known_limitations=(
                "No news classification is available.",
                "Free datasets can have survivorship and short-borrow limitations.",
            ),
        )

    def on_session_start(self, ctx: StrategyContext) -> None:
        self._session_date = ctx.session_date
        self._session_open_utc = None
        self._gap_pct = None
        self._direction = None
        self._range_high = None
        self._range_low = None
        self._traded = False

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if self._session_date != bar.session_date:
            self.on_session_start(ctx)
        history = ctx.history(bar.symbol)
        if self._session_open_utc is None:
            self._session_open_utc = bar.bar_start_utc
            previous = [item for item in history if item.session_date < bar.session_date]
            if not previous:
                return []
            previous_close = previous[-1].close
            self._gap_pct = 100.0 * (bar.open / previous_close - 1.0)
            magnitude = abs(self._gap_pct)
            if not self.params.minimum_gap_pct <= magnitude <= self.params.maximum_gap_pct:
                self._direction = None
            else:
                self._direction = "long" if self._gap_pct > 0 else "short"
        if self._direction is None or self._traded:
            return []
        confirmation_end = self._session_open_utc + timedelta(minutes=self.params.confirmation_minutes)
        if bar.bar_end_utc <= confirmation_end:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return []
        if self._range_high is None or self._range_low is None:
            return []
        local = bar.bar_end_utc.astimezone(_ET).time().replace(tzinfo=None)
        if local > self.params.latest_entry_time or ctx.position_quantity(bar.symbol) != 0:
            return []
        prior = tuple(item for item in history if item.bar_end_utc < bar.bar_end_utc)
        volume_ratio = median_volume_ratio(prior, bar.volume, 20)
        atr_value = atr(history, 14)
        if volume_ratio is None or atr_value is None or volume_ratio < self.params.minimum_volume_ratio:
            return []
        buffer_fraction = self.params.confirmation_breakout_buffer_bps / 10_000.0
        features = {
            "gap_pct": self._gap_pct,
            "confirmation_high": self._range_high,
            "confirmation_low": self._range_low,
            "volume_ratio": volume_ratio,
            "atr": atr_value,
        }
        if self._direction == "long" and bar.close > self._range_high * (1 + buffer_fraction):
            stop = bar.close - self.params.stop_atr_multiple * atr_value
            target = bar.close + self.params.reward_risk * (bar.close - stop)
            self._traded = True
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.BUY,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="GAP_UP_MOMENTUM",
                    rationale="Gap-up session confirmed above the early range.",
                    feature_snapshot=features,
                )
            ]
        if self._direction == "short" and bar.close < self._range_low * (1 - buffer_fraction):
            stop = bar.close + self.params.stop_atr_multiple * atr_value
            target = bar.close - self.params.reward_risk * (stop - bar.close)
            if target <= 0:
                return []
            self._traded = True
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.SELL,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="GAP_DOWN_MOMENTUM",
                    rationale="Gap-down session confirmed below the early range.",
                    feature_snapshot=features,
                )
            ]
        return []
