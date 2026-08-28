import pytest
from datetime import datetime, timezone, timedelta, date
from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent
from edgeback.strategy.history import CausalStrategyContext

def make_bar(start: datetime, end: datetime, close: float) -> Bar:
    return Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        interval_seconds=300,
        bar_start_utc=start,
        bar_end_utc=end,
        session_date=start.date(),
        session_type="regular",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        is_complete=True,
        source_provider="test",
        source_feed="test",
        adjustment_mode="raw",
        ingested_at_utc=datetime.now(timezone.utc)
    )

def test_causal_history_prevents_future_access():
    tz = timezone.utc
    base_time = datetime(2026, 8, 20, 14, 0, tzinfo=tz)
    
    b1 = make_bar(base_time - timedelta(minutes=10), base_time - timedelta(minutes=5), 100.0)
    b2 = make_bar(base_time - timedelta(minutes=5), base_time, 101.0)
    b3 = make_bar(base_time, base_time + timedelta(minutes=5), 102.0)
    b4 = make_bar(base_time + timedelta(minutes=5), base_time + timedelta(minutes=10), 103.0)
    
    bars = [b1, b2, b3, b4]
    
    # Engine time is exactly base_time. b2 ended exactly at base_time, so it's completed.
    # b3 ends in the future (base_time + 5m), so it is not causal yet.
    context = CausalStrategyContext(base_time, {"AAPL": bars})
    
    # Requesting last 3 bars, but only 2 are causal
    hist = context.history("AAPL", 3)
    
    assert len(hist) == 2
    assert hist[0] == b1
    assert hist[1] == b2
    
def test_history_invalid_bars_count():
    tz = timezone.utc
    base_time = datetime(2026, 8, 20, 14, 0, tzinfo=tz)
    context = CausalStrategyContext(base_time, {})
    with pytest.raises(ValueError, match="bars must be greater than 0"):
        context.history("AAPL", 0)

def test_history_unknown_symbol():
    tz = timezone.utc
    base_time = datetime(2026, 8, 20, 14, 0, tzinfo=tz)
    context = CausalStrategyContext(base_time, {})
    assert context.history("UNKNOWN", 5) == []

def test_future_mutation_sentinel_passes():
    tz = timezone.utc
    base_time = datetime(2026, 8, 20, 14, 0, tzinfo=tz)
    
    b1 = make_bar(base_time - timedelta(minutes=5), base_time, 101.0)
    bars = [b1]
    
    context = CausalStrategyContext(base_time, {"AAPL": bars})
    hist = context.history("AAPL", 1)
    
    assert len(hist) == 1
    
    # Strategy attempts to mutate the list
    hist.pop()
    
    # Original context should be unaffected
    assert len(context.history("AAPL", 1)) == 1
    
    # Strategy attempts to mutate the frozen bar
    bar = context.history("AAPL", 1)[0]
    with pytest.raises(Exception):
        # Frozen model, so setting attribute will raise
        bar.close = 999.0
    
    # The original value is unchanged
    assert context.history("AAPL", 1)[0].close == 101.0

def test_create_intent():
    tz = timezone.utc
    base_time = datetime(2026, 8, 20, 14, 0, tzinfo=tz)
    context = CausalStrategyContext(base_time, {})
    
    intent = context.create_intent(
        symbol="AAPL",
        intent_type="market",
        direction="long",
        requested_shares=10
    )
    
    assert intent.symbol == "AAPL"
    assert intent.intent_type == "market"
    assert intent.direction == "long"
    assert intent.requested_shares == 10
