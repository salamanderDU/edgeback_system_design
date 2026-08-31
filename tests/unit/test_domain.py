from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from edgeback.domain import Bar, IntentType, OrderIntent, OrderType, Side


def make_bar(**overrides: object) -> Bar:
    start = datetime(2026, 8, 28, 13, 30, tzinfo=UTC)
    payload = {
        "symbol": "spy",
        "provider_symbol": "SPY",
        "interval_seconds": 300,
        "bar_start_utc": start,
        "bar_end_utc": start + timedelta(minutes=5),
        "session_date": date(2026, 8, 28),
        "session_type": "regular",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
        "is_complete": True,
        "source_provider": "fixture",
        "source_feed": "fixture",
        "adjustment_mode": "raw",
        "ingested_at_utc": datetime(2026, 8, 29, tzinfo=UTC),
    }
    payload.update(overrides)
    return Bar.model_validate(payload)


def test_bar_normalizes_symbol_and_requires_utc() -> None:
    bar = make_bar()
    assert bar.symbol == "SPY"
    with pytest.raises(ValidationError):
        make_bar(bar_start_utc=datetime(2026, 8, 28, 13, 30))


def test_bar_rejects_invalid_ohlc_and_duration() -> None:
    with pytest.raises(ValidationError):
        make_bar(high=99.0)
    with pytest.raises(ValidationError):
        make_bar(bar_end_utc=datetime(2026, 8, 28, 13, 34, tzinfo=UTC))


def test_entry_intent_validates_stop_direction() -> None:
    now = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)
    intent = OrderIntent(
        intent_id=1,
        strategy_id="example",
        strategy_version="0.1.0",
        symbol="spy",
        side=Side.BUY,
        intent_type=IntentType.ENTRY,
        order_type=OrderType.MARKET,
        signal_time_utc=now,
        entry_reference_price=100,
        stop_loss_price=99,
        take_profit_price=102,
        reason_code="TEST",
    )
    assert intent.symbol == "SPY"
    payload = intent.model_dump(mode="python")
    payload["stop_loss_price"] = 101
    with pytest.raises(ValidationError):
        OrderIntent.model_validate(payload)
