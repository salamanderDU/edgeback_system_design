import datetime
from zoneinfo import ZoneInfo

import pytest

from edgeback.domain.bars import Bar
from edgeback.strategy.history import CausalStrategyContext
from strategies.opening_range_breakout import OpeningRangeBreakout, OpeningRangeBreakoutParameters


@pytest.fixture
def base_bars():
    tz = ZoneInfo("America/New_York")

    bars = []
    start_dt = datetime.datetime(2023, 10, 2, 9, 30, tzinfo=tz)

    # 20 warmup bars (previous session or premarket)
    for i in range(20):
        b = Bar(
            symbol="AAPL",
            provider_symbol="AAPL",
            bar_start_utc=start_dt.replace(hour=7) + datetime.timedelta(minutes=5 * i),
            bar_end_utc=start_dt.replace(hour=7) + datetime.timedelta(minutes=5 * (i + 1)),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            interval_seconds=300,
            session_type="pre",
            session_date=datetime.date(2023, 10, 2),
            is_complete=True,
            source_provider="test",
            source_feed="test",
            adjustment_mode="split_adjusted",
            ingested_at_utc=start_dt,
        )
        bars.append(b)

    # First 3 bars (15 mins) for OR (9:30 - 9:45)
    # OR will be high 102.0, low 100.0
    for i in range(3):
        b = Bar(
            symbol="AAPL",
            provider_symbol="AAPL",
            bar_start_utc=start_dt + datetime.timedelta(minutes=5 * i),
            bar_end_utc=start_dt + datetime.timedelta(minutes=5 * (i + 1)),
            open=100.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=5000,
            interval_seconds=300,
            session_type="regular",
            session_date=datetime.date(2023, 10, 2),
            is_complete=True,
            source_provider="test",
            source_feed="test",
            adjustment_mode="split_adjusted",
            ingested_at_utc=start_dt,
        )
        bars.append(b)

    return bars


def test_orb_long_breakout(base_bars):
    params = OpeningRangeBreakoutParameters()
    strategy = OpeningRangeBreakout(params)

    tz = ZoneInfo("America/New_York")
    start_dt = datetime.datetime(2023, 10, 2, 9, 30, tzinfo=tz)
    breakout_bar = Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        bar_start_utc=start_dt + datetime.timedelta(minutes=15),
        bar_end_utc=start_dt + datetime.timedelta(minutes=20),
        open=101.0,
        high=104.0,
        low=101.0,
        close=103.0,
        volume=10000,  # higher volume
        interval_seconds=300,
        session_type="regular",
        session_date=datetime.date(2023, 10, 2),
        is_complete=True,
        source_provider="test",
        source_feed="test",
        adjustment_mode="split_adjusted",
        ingested_at_utc=start_dt,
    )
    all_bars = base_bars + [breakout_bar]

    context = CausalStrategyContext(
        engine_time_utc=breakout_bar.bar_end_utc, bars_by_symbol={"AAPL": all_bars}
    )
    strategy.initialize(context)

    intents = strategy.on_bar(context, breakout_bar)

    assert len(intents) == 1
    intent = intents[0]
    assert intent.direction == "long"
    assert intent.intent_type == "market"


def test_orb_rejects_low_volume(base_bars):
    params = OpeningRangeBreakoutParameters()
    strategy = OpeningRangeBreakout(params)

    tz = ZoneInfo("America/New_York")
    start_dt = datetime.datetime(2023, 10, 2, 9, 30, tzinfo=tz)
    breakout_bar = Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        bar_start_utc=start_dt + datetime.timedelta(minutes=15),
        bar_end_utc=start_dt + datetime.timedelta(minutes=20),
        open=101.0,
        high=104.0,
        low=101.0,
        close=103.0,
        volume=100,  # low volume
        interval_seconds=300,
        session_type="regular",
        session_date=datetime.date(2023, 10, 2),
        is_complete=True,
        source_provider="test",
        source_feed="test",
        adjustment_mode="split_adjusted",
        ingested_at_utc=start_dt,
    )
    all_bars = base_bars + [breakout_bar]

    context = CausalStrategyContext(
        engine_time_utc=breakout_bar.bar_end_utc, bars_by_symbol={"AAPL": all_bars}
    )
    strategy.initialize(context)

    intents = strategy.on_bar(context, breakout_bar)
    assert len(intents) == 0


def test_orb_cutoff_time(base_bars):
    params = OpeningRangeBreakoutParameters()
    strategy = OpeningRangeBreakout(params)

    tz = ZoneInfo("America/New_York")
    start_dt = datetime.datetime(2023, 10, 2, 14, 45, tzinfo=tz)
    breakout_bar = Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        bar_start_utc=start_dt,
        bar_end_utc=start_dt + datetime.timedelta(minutes=5),
        open=101.0,
        high=104.0,
        low=101.0,
        close=103.0,
        volume=10000,
        interval_seconds=300,
        session_type="regular",
        session_date=datetime.date(2023, 10, 2),
        is_complete=True,
        source_provider="test",
        source_feed="test",
        adjustment_mode="split_adjusted",
        ingested_at_utc=start_dt,
    )
    all_bars = base_bars + [breakout_bar]

    context = CausalStrategyContext(
        engine_time_utc=breakout_bar.bar_end_utc, bars_by_symbol={"AAPL": all_bars}
    )
    strategy.initialize(context)

    # Needs to process OR first
    for b in base_bars:
        strategy.on_bar(context, b)

    intents = strategy.on_bar(context, breakout_bar)
    assert len(intents) == 0


def test_orb_max_trades(base_bars):
    params = OpeningRangeBreakoutParameters(max_trades_per_symbol_session=1)
    strategy = OpeningRangeBreakout(params)

    tz = ZoneInfo("America/New_York")
    start_dt = datetime.datetime(2023, 10, 2, 9, 30, tzinfo=tz)
    breakout_bar = Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        bar_start_utc=start_dt + datetime.timedelta(minutes=15),
        bar_end_utc=start_dt + datetime.timedelta(minutes=20),
        open=101.0,
        high=104.0,
        low=101.0,
        close=103.0,
        volume=10000,
        interval_seconds=300,
        session_type="regular",
        session_date=datetime.date(2023, 10, 2),
        is_complete=True,
        source_provider="test",
        source_feed="test",
        adjustment_mode="split_adjusted",
        ingested_at_utc=start_dt,
    )
    all_bars = base_bars + [breakout_bar]

    context = CausalStrategyContext(
        engine_time_utc=breakout_bar.bar_end_utc, bars_by_symbol={"AAPL": all_bars}
    )
    strategy.initialize(context)

    # Force state to already have a trade
    strategy.state["trades_taken_by_direction"] = {"long": 1, "short": 0}
    strategy.state["opening_range_complete"] = True
    strategy.state["opening_range_high"] = 102.0
    strategy.state["opening_range_low"] = 100.0
    strategy.state["current_session"] = datetime.date(2023, 10, 2)

    intents = strategy.on_bar(context, breakout_bar)
    assert len(intents) == 0
