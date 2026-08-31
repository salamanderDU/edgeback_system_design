"""Opening Range Breakout hypothesis strategy."""

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


class OpeningRangeBreakoutParams(StrategyParameters):
    opening_range_minutes: int = Field(default=15, ge=5, le=60)
    directions: str = "both"
    breakout_buffer_bps: float = Field(default=5.0, ge=0.0, le=50.0)
    minimum_opening_range_pct: float = Field(default=0.20, ge=0.0, le=5.0)
    maximum_opening_range_pct: float = Field(default=2.50, ge=0.1, le=20.0)
    volume_ratio_lookback_bars: int = Field(default=20, ge=5, le=100)
    minimum_volume_ratio: float = Field(default=1.20, ge=0.0, le=10.0)
    atr_period: int = Field(default=14, ge=2, le=100)
    stop_model: str = "opposite_range_or_atr"
    stop_atr_multiple: float = Field(default=0.80, ge=0.1, le=5.0)
    reward_risk: float = Field(default=1.50, ge=0.25, le=10.0)
    max_trades_per_symbol_session: int = Field(default=1, ge=1, le=10)
    close_if_not_triggered_by: time = time(14, 30)

    @field_validator("directions")
    @classmethod
    def validate_directions(cls, value: str) -> str:
        if value not in {"long", "short", "both"}:
            raise ValueError("directions must be long, short, or both")
        return value

    @field_validator("stop_model")
    @classmethod
    def validate_stop_model(cls, value: str) -> str:
        if value not in {"opposite_range", "atr", "opposite_range_or_atr"}:
            raise ValueError("invalid stop_model")
        return value

    @field_validator("close_if_not_triggered_by", mode="before")
    @classmethod
    def parse_time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def range_bounds(self) -> "OpeningRangeBreakoutParams":
        if self.minimum_opening_range_pct > self.maximum_opening_range_pct:
            raise ValueError("minimum_opening_range_pct cannot exceed maximum")
        return self


@register_strategy
class OpeningRangeBreakoutStrategy(Strategy[OpeningRangeBreakoutParams]):
    strategy_id = "opening_range_breakout"
    strategy_version = "0.1.0"
    params_model = OpeningRangeBreakoutParams

    def __init__(self, params: OpeningRangeBreakoutParams) -> None:
        super().__init__(params)
        self._session_date = None
        self._session_open_utc = None
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._trades_by_direction = {"long": 0, "short": 0}

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Opening Range Breakout",
            description=(
                "Breakout beyond the first minutes' range with causal volume and range filters."
            ),
            timeframes=("1m", "5m", "15m"),
            directions=("long", "short"),
            warmup_bars=20,
            previous_sessions_required=1,
            research_status="hypothesis",
            known_limitations=(
                "OHLCV does not reveal the intrabar breakout path.",
                "Synthetic costs replace quote data.",
                "Opening auction effects are not modeled.",
            ),
        )

    def on_session_start(self, ctx: StrategyContext) -> None:
        self._session_date = ctx.session_date
        self._session_open_utc = None
        self._range_high = None
        self._range_low = None
        self._trades_by_direction = {"long": 0, "short": 0}

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if self._session_date != bar.session_date:
            self.on_session_start(ctx)
        if self._session_open_utc is None:
            self._session_open_utc = bar.bar_start_utc
        range_end = self._session_open_utc + timedelta(minutes=self.params.opening_range_minutes)
        if bar.bar_end_utc <= range_end:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return []
        if self._range_high is None or self._range_low is None:
            return []
        local_time = bar.bar_end_utc.astimezone(_ET).time().replace(tzinfo=None)
        if local_time > self.params.close_if_not_triggered_by:
            return []
        if ctx.position_quantity(bar.symbol) != 0:
            return []

        midpoint = (self._range_high + self._range_low) / 2.0
        width_pct = 100.0 * (self._range_high - self._range_low) / midpoint
        if not (
            self.params.minimum_opening_range_pct
            <= width_pct
            <= self.params.maximum_opening_range_pct
        ):
            return []
        history = ctx.history(bar.symbol)
        prior = tuple(item for item in history if item.bar_end_utc < bar.bar_end_utc)
        volume_ratio = median_volume_ratio(
            prior, bar.volume, self.params.volume_ratio_lookback_bars
        )
        atr_value = atr(history, self.params.atr_period)
        if volume_ratio is None or atr_value is None or volume_ratio < self.params.minimum_volume_ratio:
            return []
        buffer_fraction = self.params.breakout_buffer_bps / 10_000.0
        long_level = self._range_high * (1.0 + buffer_fraction)
        short_level = self._range_low * (1.0 - buffer_fraction)

        if (
            self.params.directions in {"long", "both"}
            and bar.close > long_level
            and self._trades_by_direction["long"] < self.params.max_trades_per_symbol_session
        ):
            stop = self._long_stop(bar.close, atr_value)
            if stop >= bar.close:
                return []
            risk = bar.close - stop
            target = bar.close + self.params.reward_risk * risk
            self._trades_by_direction["long"] += 1
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.BUY,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="ORB_LONG_BREAKOUT",
                    rationale="Close broke above the opening range with elevated volume.",
                    feature_snapshot=self._features(
                        width_pct, volume_ratio, atr_value, long_level, stop
                    ),
                )
            ]
        if (
            self.params.directions in {"short", "both"}
            and bar.close < short_level
            and self._trades_by_direction["short"] < self.params.max_trades_per_symbol_session
        ):
            stop = self._short_stop(bar.close, atr_value)
            if stop <= bar.close:
                return []
            risk = stop - bar.close
            target = bar.close - self.params.reward_risk * risk
            if target <= 0:
                return []
            self._trades_by_direction["short"] += 1
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    side=Side.SELL,
                    sizing_model="risk_per_trade",
                    entry_reference_price=bar.close,
                    stop_loss_price=stop,
                    take_profit_price=target,
                    reason_code="ORB_SHORT_BREAKOUT",
                    rationale="Close broke below the opening range with elevated volume.",
                    feature_snapshot=self._features(
                        width_pct, volume_ratio, atr_value, short_level, stop
                    ),
                )
            ]
        return []

    def _long_stop(self, reference: float, atr_value: float) -> float:
        assert self._range_low is not None
        atr_stop = reference - atr_value * self.params.stop_atr_multiple
        if self.params.stop_model == "opposite_range":
            return self._range_low
        if self.params.stop_model == "atr":
            return atr_stop
        return max(self._range_low, atr_stop)

    def _short_stop(self, reference: float, atr_value: float) -> float:
        assert self._range_high is not None
        atr_stop = reference + atr_value * self.params.stop_atr_multiple
        if self.params.stop_model == "opposite_range":
            return self._range_high
        if self.params.stop_model == "atr":
            return atr_stop
        return min(self._range_high, atr_stop)

    def _features(
        self,
        width_pct: float,
        volume_ratio: float,
        atr_value: float,
        breakout_level: float,
        stop: float,
    ) -> dict[str, float]:
        assert self._range_high is not None and self._range_low is not None
        return {
            "opening_range_high": self._range_high,
            "opening_range_low": self._range_low,
            "opening_range_width_pct": width_pct,
            "volume_ratio": volume_ratio,
            "atr": atr_value,
            "breakout_level": breakout_level,
            "stop_reference": stop,
        }
