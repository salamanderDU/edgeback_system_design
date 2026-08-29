from datetime import UTC, date, datetime, timedelta

import pytest

from edgeback.domain.bars import Bar
from edgeback.features import (
    calculate_atr,
    calculate_opening_range,
    calculate_volume_ratio,
)


@pytest.fixture
def base_time():
    return datetime(2026, 8, 24, 13, 30, tzinfo=UTC)  # 9:30 AM NY time (EDT, UTC-4)


@pytest.fixture
def sample_bars(base_time):
    bars = []
    for i in range(10):
        start = base_time + timedelta(minutes=i * 5)
        end = start + timedelta(minutes=5)
        bars.append(
            Bar(
                symbol="TEST",
                provider_symbol="TEST",
                interval_seconds=300,
                bar_start_utc=start,
                bar_end_utc=end,
                session_date=date(2026, 8, 24),
                session_type="regular",
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=1000 + i * 100,
                is_complete=True,
                source_provider="test",
                source_feed="test",
                adjustment_mode="raw",
                ingested_at_utc=datetime.now(UTC),
            )
        )
    return bars


def test_calculate_opening_range(sample_bars):
    # First 15 mins = 3 bars (0, 1, 2)
    # Highs: 102, 103, 104 -> max 104
    # Lows: 99, 100, 101 -> min 99
    high, low = calculate_opening_range(sample_bars, 15)
    assert high == 104.0
    assert low == 99.0


def test_calculate_opening_range_incomplete_bar(sample_bars):
    # Make the 3rd bar incomplete
    sample_bars[2] = sample_bars[2].model_copy(update={"is_complete": False})
    high, low = calculate_opening_range(sample_bars, 15)
    # Only bars 0, 1 should be included as bar 2 is incomplete
    # Highs: 102, 103 -> max 103
    # Lows: 99, 100 -> min 99
    assert high == 103.0
    assert low == 99.0


def test_calculate_opening_range_empty():
    high, low = calculate_opening_range([], 15)
    assert high is None
    assert low is None


def test_calculate_atr(sample_bars):
    # TRs for the bars:
    # 0: 102 - 99 = 3
    # 1: max(103-100, abs(103-101), abs(100-101)) = max(3, 2, 1) = 3
    # All TRs will be 3 in this linear progression
    atr = calculate_atr(sample_bars, 5)
    assert atr == 3.0


def test_calculate_atr_insufficient_bars(sample_bars):
    atr = calculate_atr(sample_bars[:4], 5)
    assert atr is None


def test_calculate_volume_ratio(sample_bars):
    current = sample_bars[5]  # volume 1500
    lookback = sample_bars[:5]  # volumes 1000, 1100, 1200, 1300, 1400. Median = 1200
    ratio = calculate_volume_ratio(current, lookback)
    assert ratio == 1500 / 1200


def test_calculate_volume_ratio_empty_lookback(sample_bars):
    ratio = calculate_volume_ratio(sample_bars[0], [])
    assert ratio is None
