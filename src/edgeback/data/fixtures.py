from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from edgeback.calendar import XNYSCalendar
from edgeback.data.providers.interfaces import ProviderCapabilities
from edgeback.domain import Bar, SessionType


def fixture_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="fixture",
        feeds=("fixture",),
        intervals=("1m", "5m", "15m"),
        earliest_history="synthetic",
        limitations=("Synthetic deterministic data for mechanical validation only.",),
    )


def generate_fixture_bars(
    *,
    symbols: tuple[str, ...] = ("TESTA", "TESTB"),
    first_session: date = date(2025, 1, 6),
    session_count: int = 3,
    interval_seconds: int = 300,
) -> tuple[Bar, ...]:
    if session_count < 1:
        raise ValueError("session_count must be positive")
    calendar = XNYSCalendar()
    sessions = calendar.sessions(first_session, first_session + timedelta(days=session_count * 3 + 10))[
        :session_count
    ]
    ingested = datetime(2026, 8, 30, tzinfo=UTC)
    bars: list[Bar] = []
    for symbol_index, raw_symbol in enumerate(symbols):
        symbol = raw_symbol.strip().upper()
        base = 100.0 + symbol_index * 25.0
        previous_close = base
        for session_index, session in enumerate(sessions):
            starts = calendar.expected_bar_starts(session.session_date, interval_seconds)
            for bar_index, start in enumerate(starts):
                open_price, high, low, close, volume = _fixture_ohlcv(
                    base=base,
                    previous_close=previous_close,
                    session_index=session_index,
                    bar_index=bar_index,
                )
                end = start + timedelta(seconds=interval_seconds)
                bars.append(
                    Bar(
                        symbol=symbol,
                        provider_symbol=symbol,
                        interval_seconds=interval_seconds,
                        bar_start_utc=start,
                        bar_end_utc=end,
                        session_date=session.session_date,
                        session_type=SessionType.REGULAR,
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        vwap=None,
                        trade_count=None,
                        is_complete=True,
                        source_provider="fixture",
                        source_feed="fixture",
                        adjustment_mode="raw",
                        ingested_at_utc=ingested,
                    )
                )
                previous_close = close
    return tuple(sorted(bars, key=lambda item: (item.bar_end_utc, item.symbol)))


def _fixture_ohlcv(
    *,
    base: float,
    previous_close: float,
    session_index: int,
    bar_index: int,
) -> tuple[float, float, float, float, int]:
    cycle = session_index % 3
    if bar_index < 3:
        offsets = (0.0, 0.04, -0.02)
        close = base + offsets[bar_index]
        open_price = previous_close if bar_index else base
        return open_price, max(open_price, close, base + 0.20), min(open_price, close, base - 0.20), close, 1000

    if cycle == 1 and bar_index == 3:
        close = base + 0.42
        return base + 0.02, base + 0.46, base - 0.01, close, 100_000
    if cycle == 1 and bar_index == 4:
        open_price = base + 0.44
        close = base + 0.78
        return open_price, base + 1.00, base + 0.36, close, 100_000
    if cycle == 2 and bar_index == 3:
        close = base - 0.42
        return base - 0.02, base + 0.01, base - 0.46, close, 100_000
    if cycle == 2 and bar_index == 4:
        open_price = base - 0.44
        close = base - 0.78
        return open_price, base - 0.36, base - 1.00, close, 100_000

    if cycle == 1:
        anchor = base + 0.80
    elif cycle == 2:
        anchor = base - 0.80
    else:
        anchor = base
    close = anchor + 0.03 * math.sin(bar_index / 4.0)
    open_price = previous_close
    high = max(open_price, close) + 0.08
    low = min(open_price, close) - 0.08
    return open_price, high, low, close, 1000
