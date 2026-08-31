"""Optional live-provider smoke tests.

Run explicitly with:
    EDGEBACK_RUN_NETWORK_TESTS=1 pytest -m network tests/network
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from edgeback.data.providers import AlpacaIEXProvider, BarRequest, YFinanceProvider

pytestmark = pytest.mark.network


def _request(symbol: str, *, provider: str, feed: str) -> BarRequest:
    end = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=20)
    start = end - timedelta(days=7)
    return BarRequest(
        symbols=(symbol,),
        interval="5m",
        start_utc=start,
        end_utc=end,
        include_extended_hours=False,
        adjustment_mode="split_adjusted",
        feed=feed,
    )


@pytest.mark.skipif(
    os.getenv("EDGEBACK_RUN_NETWORK_TESTS") != "1",
    reason="network smoke tests are opt-in",
)
def test_yfinance_live_smoke() -> None:
    pytest.importorskip("yfinance")
    batch = YFinanceProvider().fetch_bars(_request("SPY", provider="yfinance", feed="yahoo"))
    assert not batch.frame.empty
    assert batch.provider_id == "yfinance"
    assert batch.feed == "yahoo"


@pytest.mark.skipif(
    os.getenv("EDGEBACK_RUN_NETWORK_TESTS") != "1"
    or not os.getenv("ALPACA_API_KEY")
    or not os.getenv("ALPACA_SECRET_KEY"),
    reason="Alpaca smoke test requires explicit opt-in and credentials",
)
def test_alpaca_iex_live_smoke() -> None:
    batch = AlpacaIEXProvider().fetch_bars(_request("SPY", provider="alpaca", feed="iex"))
    assert not batch.frame.empty
    assert batch.provider_id == "alpaca"
    assert batch.feed == "iex"
