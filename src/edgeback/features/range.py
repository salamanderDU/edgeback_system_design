from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from edgeback.domain import Bar


def opening_range(
    bars: Sequence[Bar], *, session_open_utc: datetime, minutes: int
) -> tuple[float, float] | None:
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    cutoff = session_open_utc.timestamp() + minutes * 60
    selected = [
        bar
        for bar in bars
        if bar.bar_start_utc >= session_open_utc and bar.bar_end_utc.timestamp() <= cutoff
    ]
    if not selected:
        return None
    return max(bar.high for bar in selected), min(bar.low for bar in selected)
