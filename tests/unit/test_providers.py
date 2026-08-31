from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from edgeback.data.providers.alpaca_provider import AlpacaIEXProvider
from edgeback.data.providers.interfaces import BarRequest
from edgeback.data.providers.yfinance_provider import YFinanceProvider
from edgeback.errors import DataUnavailableError


def request(provider: str) -> BarRequest:
    return BarRequest(
        symbols=("AAA",),
        interval="5m",
        start_utc=datetime(2026, 8, 1, tzinfo=UTC),
        end_utc=datetime(2026, 8, 2, tzinfo=UTC),
        feed="yahoo" if provider == "yfinance" else "iex",
        adjustment_mode="split_adjusted",
    )


def test_yfinance_adapter_uses_explicit_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def download(**kwargs: object) -> pd.DataFrame:
        observed.update(kwargs)
        index = pd.DatetimeIndex(["2026-08-01T13:30:00Z"], name="Datetime")
        return pd.DataFrame(
            {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [1000]},
            index=index,
        )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    batch = YFinanceProvider().fetch_bars(request("yfinance"))
    assert batch.feed == "yahoo"
    assert batch.dataframe().iloc[0]["symbol"] == "AAA"
    for key in ("auto_adjust", "back_adjust", "actions", "repair", "prepost", "threads", "timeout"):
        assert key in observed


def test_yfinance_rejects_overlong_intraday_request() -> None:
    payload = request("yfinance").model_copy(
        update={"start_utc": datetime(2026, 1, 1, tzinfo=UTC), "end_utc": datetime(2026, 8, 1, tzinfo=UTC)}
    )
    with pytest.raises(DataUnavailableError):
        YFinanceProvider().fetch_bars(payload)


class _Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=httpx.Request("GET", "https://example.test"), response=httpx.Response(self.status_code))

    def json(self) -> dict[str, object]:
        return self.payload


class _Client:
    def __init__(self) -> None:
        self.headers: dict[str, str] | None = None
        self.params: dict[str, object] | None = None

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, object]) -> _Response:
        self.headers = headers
        self.params = dict(params)
        return _Response(
            {
                "bars": {
                    "AAA": [
                        {"t": "2026-08-01T13:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000, "n": 10, "vw": 100.2}
                    ]
                },
                "next_page_token": None,
            }
        )


def test_alpaca_adapter_requires_environment_and_pins_iex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(DataUnavailableError):
        AlpacaIEXProvider(client=_Client()).fetch_bars(request("alpaca"))

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    client = _Client()
    batch = AlpacaIEXProvider(client=client).fetch_bars(request("alpaca"))
    assert batch.feed == "iex"
    assert client.params is not None and client.params["feed"] == "iex"
    assert batch.metadata["credentials_source"] == "environment"
    # Payload metadata and rows never contain the secret itself.
    assert "test-secret" not in repr(batch.model_dump())
