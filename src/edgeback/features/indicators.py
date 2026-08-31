from __future__ import annotations

import statistics
from collections.abc import Sequence

from edgeback.domain import Bar


def true_range(current: Bar, previous_close: float | None) -> float:
    if previous_close is None:
        return current.high - current.low
    return max(
        current.high - current.low,
        abs(current.high - previous_close),
        abs(current.low - previous_close),
    )


def atr(bars: Sequence[Bar], period: int) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(bars) < period:
        return None
    selected = bars[-period:]
    ranges: list[float] = []
    previous_close: float | None = bars[-period - 1].close if len(bars) > period else None
    for bar in selected:
        ranges.append(true_range(bar, previous_close))
        previous_close = bar.close
    return sum(ranges) / len(ranges)


def median_volume_ratio(history_before_current: Sequence[Bar], current_volume: int, lookback: int) -> float | None:
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if len(history_before_current) < lookback:
        return None
    baseline = statistics.median(bar.volume for bar in history_before_current[-lookback:])
    if baseline <= 0:
        return None
    return float(current_volume) / float(baseline)


def session_vwap(bars: Sequence[Bar]) -> float | None:
    if not bars:
        return None
    total_volume = sum(bar.volume for bar in bars)
    if total_volume <= 0:
        return None
    dollar_volume = sum(((bar.high + bar.low + bar.close) / 3.0) * bar.volume for bar in bars)
    return dollar_volume / total_volume


def vwap_series(bars: Sequence[Bar]) -> tuple[float | None, ...]:
    total_volume = 0
    dollar_volume = 0.0
    output: list[float | None] = []
    for bar in bars:
        total_volume += bar.volume
        dollar_volume += ((bar.high + bar.low + bar.close) / 3.0) * bar.volume
        output.append(dollar_volume / total_volume if total_volume > 0 else None)
    return tuple(output)
