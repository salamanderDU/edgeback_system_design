"""Causal within-session OHLCV resampling."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from edgeback.domain import Bar
from edgeback.errors import DataValidationError


def resample_bars(
    bars: tuple[Bar, ...] | list[Bar],
    *,
    target_interval_seconds: int,
    incomplete_group_policy: str = "fail",
) -> tuple[Bar, ...]:
    source = tuple(sorted(bars, key=lambda item: (item.symbol, item.session_date, item.bar_start_utc)))
    if not source:
        return ()
    if incomplete_group_policy not in {"fail", "drop"}:
        raise DataValidationError("incomplete_group_policy must be fail or drop")
    source_intervals = {bar.interval_seconds for bar in source}
    if len(source_intervals) != 1:
        raise DataValidationError("Cannot resample mixed source intervals")
    source_interval = next(iter(source_intervals))
    if target_interval_seconds <= source_interval or target_interval_seconds % source_interval:
        raise DataValidationError("Target interval must be an integer multiple of the source interval")
    expected = target_interval_seconds // source_interval
    identities = {(bar.source_provider, bar.source_feed, bar.adjustment_mode) for bar in source}
    if len(identities) != 1:
        raise DataValidationError("Cannot resample mixed provider/feed/adjustment data")

    by_session: dict[tuple[str, object], list[Bar]] = defaultdict(list)
    for bar in source:
        by_session[(bar.symbol, bar.session_date)].append(bar)
    output: list[Bar] = []
    for key in sorted(by_session, key=lambda item: (item[1], item[0])):
        session_bars = sorted(by_session[key], key=lambda item: item.bar_start_utc)
        session_start = session_bars[0].bar_start_utc
        groups: dict[int, list[Bar]] = defaultdict(list)
        for bar in session_bars:
            offset = int((bar.bar_start_utc - session_start).total_seconds())
            groups[offset // target_interval_seconds].append(bar)
        for group_number in sorted(groups):
            group = sorted(groups[group_number], key=lambda item: item.bar_start_utc)
            contiguous = all(
                right.bar_start_utc - left.bar_start_utc == timedelta(seconds=source_interval)
                for left, right in zip(group, group[1:])
            )
            if len(group) != expected or not contiguous:
                if incomplete_group_policy == "drop":
                    continue
                raise DataValidationError(
                    f"Incomplete resample group for {key[0]} {key[1]} group {group_number}: "
                    f"expected {expected}, observed {len(group)}"
                )
            first, last = group[0], group[-1]
            trade_counts = [item.trade_count for item in group]
            output.append(
                Bar(
                    symbol=first.symbol,
                    provider_symbol=first.provider_symbol,
                    interval_seconds=target_interval_seconds,
                    bar_start_utc=first.bar_start_utc,
                    bar_end_utc=first.bar_start_utc + timedelta(seconds=target_interval_seconds),
                    session_date=first.session_date,
                    session_type=first.session_type,
                    open=first.open,
                    high=max(item.high for item in group),
                    low=min(item.low for item in group),
                    close=last.close,
                    volume=sum(item.volume for item in group),
                    # Provider VWAP is not silently synthesized during resampling.
                    vwap=None,
                    trade_count=(sum(int(item) for item in trade_counts if item is not None) if all(item is not None for item in trade_counts) else None),
                    is_complete=all(item.is_complete for item in group),
                    source_provider=first.source_provider,
                    source_feed=first.source_feed,
                    adjustment_mode=first.adjustment_mode,
                    ingested_at_utc=max(item.ingested_at_utc for item in group),
                )
            )
    return tuple(sorted(output, key=lambda item: (item.bar_end_utc, item.symbol)))
