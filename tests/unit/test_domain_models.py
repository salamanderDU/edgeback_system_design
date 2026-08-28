from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from edgeback.domain.bars import Bar
from edgeback.domain.fills import Fill
from edgeback.domain.orders import Order


def dummy_dt(offset_hours: int = 0) -> datetime:
    return datetime(2025, 1, 1, 9 + offset_hours, 30, tzinfo=UTC)


def test_bar_valid() -> None:
    bar = Bar(
        symbol="AAPL",
        provider_symbol="AAPL",
        interval_seconds=300,
        bar_start_utc=dummy_dt(),
        bar_end_utc=dummy_dt(1),
        session_date=date(2025, 1, 1),
        session_type="regular",
        open=150.0,
        high=155.0,
        low=149.0,
        close=151.0,
        volume=1000,
        is_complete=True,
        source_provider="yfinance",
        source_feed="yahoo",
        adjustment_mode="split_adjusted",
        ingested_at_utc=dummy_dt(2),
    )
    assert bar.symbol == "AAPL"


def test_bar_invalid_ohlc() -> None:
    with pytest.raises(ValidationError, match="must be between Low"):
        Bar(
            symbol="AAPL",
            provider_symbol="AAPL",
            interval_seconds=300,
            bar_start_utc=dummy_dt(),
            bar_end_utc=dummy_dt(1),
            session_date=date(2025, 1, 1),
            session_type="regular",
            open=140.0,  # Open less than low!
            high=155.0,
            low=149.0,
            close=151.0,
            volume=1000,
            is_complete=True,
            source_provider="yfinance",
            source_feed="yahoo",
            adjustment_mode="split_adjusted",
            ingested_at_utc=dummy_dt(2),
        )


def test_bar_invalid_timezone() -> None:
    naive_dt = datetime(2025, 1, 1, 9, 30)  # No tzinfo
    with pytest.raises(ValidationError, match="must be timezone-aware"):
        Bar(
            symbol="AAPL",
            provider_symbol="AAPL",
            interval_seconds=300,
            bar_start_utc=naive_dt,
            bar_end_utc=dummy_dt(1),
            session_date=date(2025, 1, 1),
            session_type="regular",
            open=150.0,
            high=155.0,
            low=149.0,
            close=151.0,
            volume=1000,
            is_complete=True,
            source_provider="yfinance",
            source_feed="yahoo",
            adjustment_mode="split_adjusted",
            ingested_at_utc=dummy_dt(2),
        )


def test_order_serialization() -> None:
    order = Order(id="ord-1", symbol="TSLA", direction="long", order_type="market", shares=100)
    assert order.status == "pending"
    assert order.reason == ""


def test_fill_serialization() -> None:
    fill = Fill(
        id="fill-1",
        order_id="ord-1",
        symbol="TSLA",
        timestamp_utc=dummy_dt(),
        direction="long",
        action="buy",
        shares=100,
        fill_price=200.50,
        commission_usd=0.0,
        slippage_usd=1.5,
        spread_usd=2.0,
    )
    assert fill.commission_usd == 0.0
