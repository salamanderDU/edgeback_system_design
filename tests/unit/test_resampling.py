from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from edgeback.data import resample_bars
from edgeback.domain import Bar
from edgeback.errors import DataValidationError


def _bar(start: datetime, value: float) -> Bar:
    return Bar(
        symbol="AAA",
        provider_symbol="AAA",
        interval_seconds=60,
        bar_start_utc=start,
        bar_end_utc=start + timedelta(minutes=1),
        session_date=start.date(),
        session_type="regular",
        open=value,
        high=value + 1,
        low=value - 1,
        close=value + 0.5,
        volume=100,
        source_provider="fixture",
        source_feed="fixture",
        adjustment_mode="raw",
        ingested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_resampling_aggregates_inside_session_only() -> None:
    start = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
    bars = tuple(_bar(start + timedelta(minutes=index), 100 + index) for index in range(10))
    result = resample_bars(bars, target_interval_seconds=300)
    assert len(result) == 2
    assert result[0].open == 100
    assert result[0].close == 104.5
    assert result[0].volume == 500
    assert result[0].session_date == date(2025, 1, 6)


def test_resampling_never_fills_missing_components() -> None:
    start = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
    bars = tuple(_bar(start + timedelta(minutes=index), 100 + index) for index in (0, 1, 3, 4))
    with pytest.raises(DataValidationError):
        resample_bars(bars, target_interval_seconds=300)
    assert resample_bars(bars, target_interval_seconds=300, incomplete_group_policy="drop") == ()
