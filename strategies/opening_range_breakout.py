import datetime
import zoneinfo
from typing import Literal

from pydantic import Field

from edgeback.config.models import BaseStrictModel
from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent
from edgeback.features.indicators import calculate_atr, calculate_volume_ratio
from edgeback.features.range import calculate_opening_range
from edgeback.strategy.base import Strategy
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata
from edgeback.strategy.registry import register_strategy


class OpeningRangeBreakoutParameters(BaseStrictModel):
    opening_range_minutes: int = Field(15, ge=5, le=60)
    directions: Literal["long", "short", "both"] = Field("both")
    breakout_buffer_bps: float = Field(5.0, ge=0.0, le=50.0)
    minimum_opening_range_pct: float = Field(0.20, ge=0.0, le=5.0)
    maximum_opening_range_pct: float = Field(2.50, ge=0.1, le=20.0)
    volume_ratio_lookback_bars: int = Field(20, ge=5, le=100)
    minimum_volume_ratio: float = Field(1.20, ge=0.0, le=10.0)
    atr_period: int = Field(14, ge=2, le=100)
    stop_model: Literal["opposite_range", "atr", "opposite_range_or_atr"] = Field(
        "opposite_range_or_atr"
    )
    stop_atr_multiple: float = Field(0.80, ge=0.1, le=5.0)
    reward_risk: float = Field(1.50, ge=0.25, le=10.0)
    max_trades_per_symbol_session: int = Field(1, ge=1, le=10)
    close_if_not_triggered_by: str = Field("14:30")  # local_time string


@register_strategy
class OpeningRangeBreakout(Strategy[OpeningRangeBreakoutParameters]):
    strategy_id = "opening_range_breakout"
    strategy_version = "0.1.0"
    params_model = OpeningRangeBreakoutParameters

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Opening Range Breakout",
            scope="per_symbol",
            warmup_bars=20,
        )

    def initialize(self, ctx: StrategyContext) -> None:
        self.state = {
            "opening_range_high": None,
            "opening_range_low": None,
            "opening_range_complete": False,
            "trades_taken_by_direction": {"long": 0, "short": 0},
            "current_session": None,
        }

    def on_session_start(self, ctx: StrategyContext) -> None:
        self.state["opening_range_high"] = None
        self.state["opening_range_low"] = None
        self.state["opening_range_complete"] = False
        self.state["trades_taken_by_direction"] = {"long": 0, "short": 0}
        self.state["current_session"] = None

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        params = self.params

        # Check session boundary fallback just in case
        if self.state["current_session"] != bar.session_date:
            self.state["current_session"] = bar.session_date
            self.state["opening_range_high"] = None
            self.state["opening_range_low"] = None
            self.state["opening_range_complete"] = False
            self.state["trades_taken_by_direction"] = {"long": 0, "short": 0}

        intents: list[OrderIntent] = []

        cutoff_time_str = params.close_if_not_triggered_by
        cutoff_hour, cutoff_minute = map(int, cutoff_time_str.split(":"))

        # Convert bar_end_utc to exchange timezone
        tz = zoneinfo.ZoneInfo("America/New_York")
        local_time = bar.bar_end_utc.astimezone(tz).time()
        cutoff_time = datetime.time(cutoff_hour, cutoff_minute)

        bars = ctx.history(bar.symbol, 100)  # Fetch recent bars for OR and ATR

        if not self.state["opening_range_complete"]:
            or_high, or_low = calculate_opening_range(bars, params.opening_range_minutes)
            if or_high is not None and or_low is not None:
                # Is OR complete? Check if current bar end time is past the OR minutes.
                regular_bars = [
                    b
                    for b in bars
                    if b.session_type == "regular" and b.session_date == bar.session_date
                ]
                if regular_bars:
                    session_start_time = regular_bars[0].bar_start_utc
                    if bar.bar_end_utc.timestamp() >= session_start_time.timestamp() + (
                        params.opening_range_minutes * 60
                    ):
                        or_width_pct = (or_high - or_low) / or_low * 100
                        if (
                            params.minimum_opening_range_pct
                            <= or_width_pct
                            <= params.maximum_opening_range_pct
                        ):
                            self.state["opening_range_high"] = or_high
                            self.state["opening_range_low"] = or_low
                            self.state["opening_range_complete"] = True
                        else:
                            self.state["opening_range_complete"] = "REJECTED"

        if self.state["opening_range_complete"] is not True:
            return []

        if local_time > cutoff_time:
            return []

        total_trades = (
            self.state["trades_taken_by_direction"]["long"]
            + self.state["trades_taken_by_direction"]["short"]
        )
        if total_trades >= params.max_trades_per_symbol_session:
            return []

        or_high = self.state["opening_range_high"]
        or_low = self.state["opening_range_low"]

        lookback = (
            bars[-params.volume_ratio_lookback_bars - 1 : -1]
            if len(bars) > params.volume_ratio_lookback_bars
            else []
        )
        vr = calculate_volume_ratio(bar, lookback)
        if vr is None or vr < params.minimum_volume_ratio:
            return []

        atr = calculate_atr(bars, params.atr_period)
        if atr is None:
            return []

        buffer = or_high * (params.breakout_buffer_bps / 10000)

        is_long_valid = (
            params.directions in ["long", "both"]
            and self.state["trades_taken_by_direction"]["long"] == 0
        )
        is_short_valid = (
            params.directions in ["short", "both"]
            and self.state["trades_taken_by_direction"]["short"] == 0
        )

        signal_dir = None
        entry_price = bar.close
        stop_price = 0.0

        if is_long_valid and bar.close > (or_high + buffer):
            signal_dir = "long"
            if params.stop_model == "opposite_range":
                stop_price = or_low
            elif params.stop_model == "atr":
                stop_price = entry_price - (atr * params.stop_atr_multiple)
            else:  # opposite_range_or_atr
                stop_price = max(or_low, entry_price - (atr * params.stop_atr_multiple))

            risk = entry_price - stop_price
            if risk <= 0:
                return []

        elif is_short_valid and bar.close < (or_low - buffer):
            signal_dir = "short"
            if params.stop_model == "opposite_range":
                stop_price = or_high
            elif params.stop_model == "atr":
                stop_price = entry_price + (atr * params.stop_atr_multiple)
            else:
                stop_price = min(or_high, entry_price + (atr * params.stop_atr_multiple))

            risk = stop_price - entry_price
            if risk <= 0:
                return []

        if signal_dir:
            self.state["trades_taken_by_direction"][signal_dir] += 1

            target_price = None
            if stop_price > 0:
                risk_distance = abs(entry_price - stop_price)
                if signal_dir == "long":
                    target_price = entry_price + params.reward_risk * risk_distance
                else:
                    target_price = entry_price - params.reward_risk * risk_distance

            intent = ctx.create_intent(
                symbol=bar.symbol,
                direction=signal_dir,
                intent_type="market",
                stop_price=stop_price if stop_price > 0 else None,
                take_profit_price=target_price,
            )
            intents.append(intent)

        return intents
