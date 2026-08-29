from collections.abc import Sequence

from edgeback.domain.bars import Bar


def calculate_opening_range(
    bars: Sequence[Bar], opening_range_minutes: int
) -> tuple[float | None, float | None]:
    """
    Calculate the high and low of the opening range.
    The opening range consists of all complete 'regular' session bars whose interval lies
    entirely within the first `opening_range_minutes` of the regular session.
    """

    if not bars:
        return None, None

    regular_bars = [b for b in bars if b.session_type == "regular" and b.is_complete]
    if not regular_bars:
        return None, None

    session_start = regular_bars[0].bar_start_utc
    cutoff_time = session_start.timestamp() + (opening_range_minutes * 60)

    or_bars = [b for b in regular_bars if b.bar_end_utc.timestamp() <= cutoff_time]

    if not or_bars:
        return None, None

    or_high = max(b.high for b in or_bars)
    or_low = min(b.low for b in or_bars)

    return or_high, or_low
