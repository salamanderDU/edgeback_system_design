import statistics
from typing import Sequence
from edgeback.domain.bars import Bar

def true_range(bar: Bar, prev_bar: Bar | None = None) -> float:
    """Calculate True Range for a bar."""
    if prev_bar is None:
        return bar.high - bar.low
    
    return max(
        bar.high - bar.low,
        abs(bar.high - prev_bar.close),
        abs(bar.low - prev_bar.close)
    )

def calculate_atr(bars: Sequence[Bar], period: int) -> float | None:
    """
    Calculate Average True Range (ATR) using simple moving average.
    Returns None if fewer than `period` bars are provided.
    """
    if len(bars) < period:
        return None
        
    trs = []
    for i in range(len(bars)):
        prev = bars[i-1] if i > 0 else None
        trs.append(true_range(bars[i], prev))
        
    # Use SMA for the last 'period' true ranges
    return sum(trs[-period:]) / period

def calculate_volume_ratio(current_bar: Bar, lookback_bars: Sequence[Bar]) -> float | None:
    """
    Calculate the ratio of the current bar's volume to the median volume of the lookback_bars.
    Returns None if lookback_bars is empty or if median volume is 0.
    """
    if not lookback_bars:
        return None
        
    median_vol = statistics.median(b.volume for b in lookback_bars)
    if median_vol == 0:
        return None
        
    return current_bar.volume / median_vol
