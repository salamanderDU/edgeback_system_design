from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pandas as pd

from edgeback.data.providers.interfaces import (
    BarRequest,
    ProviderCapabilities,
    ProviderSymbol,
    RawBarBatch,
)
from edgeback.errors import DataUnavailableError
from edgeback.utils import stable_hash


class AlpacaIEXProvider:
    provider_id = "alpaca"
    endpoint = "https://data.alpaca.markets/v2/stocks/bars"

    def __init__(self, *, client: httpx.Client | None = None, max_retries: int = 3) -> None:
        self._client = client
        self.max_retries = max_retries

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            feeds=("iex",),
            intervals=("1m", "5m", "15m"),
            earliest_history="2016 according to the referenced plan documentation",
            latest_data_delay_minutes=15,
            rate_limit_per_minute=200,
            limitations=(
                "Free equity feed is IEX, not consolidated SIP.",
                "Volume-sensitive results are not directly comparable with consolidated data.",
                "Credentials are required through environment variables.",
            ),
        )

    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol:
        canonical = canonical_symbol.strip().upper()
        return ProviderSymbol(canonical_symbol=canonical, provider_symbol=canonical)

    def _credentials(self) -> tuple[str, str]:
        key = os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise DataUnavailableError(
                "Alpaca credentials are missing; set ALPACA_API_KEY and ALPACA_SECRET_KEY"
            )
        return key, secret

    def fetch_bars(self, request: BarRequest) -> RawBarBatch:
        if request.feed.lower() != "iex":
            raise DataUnavailableError("Alpaca free adapter requires feed=iex")
        key, secret = self._credentials()
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        timeframe = {"1m": "1Min", "5m": "5Min", "15m": "15Min"}.get(request.interval)
        if timeframe is None:
            raise DataUnavailableError(f"Unsupported Alpaca interval: {request.interval}")
        params: dict[str, Any] = {
            "symbols": ",".join(request.symbols),
            "timeframe": timeframe,
            "start": request.start_utc.isoformat().replace("+00:00", "Z"),
            "end": request.end_utc.isoformat().replace("+00:00", "Z"),
            "adjustment": "split" if request.adjustment_mode == "split_adjusted" else "raw",
            "feed": "iex",
            "limit": 10_000,
            "sort": "asc",
        }
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        own_client = self._client is None
        client = self._client or httpx.Client(timeout=30)
        try:
            while True:
                if page_token:
                    params["page_token"] = page_token
                payload = self._request_with_retries(client, headers, params)
                bars = payload.get("bars", {})
                if not isinstance(bars, dict):
                    raise DataUnavailableError("Unexpected Alpaca bars response")
                for symbol in sorted(bars):
                    for item in bars[symbol]:
                        rows.append(
                            {
                                "timestamp": item["t"],
                                "symbol": symbol,
                                "provider_symbol": symbol,
                                "open": item["o"],
                                "high": item["h"],
                                "low": item["l"],
                                "close": item["c"],
                                "volume": item["v"],
                                "trade_count": item.get("n"),
                                "vwap": item.get("vw"),
                            }
                        )
                page_token = payload.get("next_page_token")
                if not page_token:
                    break
        finally:
            if own_client:
                client.close()
        if not rows:
            raise DataUnavailableError("Alpaca returned no bars")
        frame = pd.DataFrame.from_records(rows).sort_values(["timestamp", "symbol"], kind="stable")
        request_id = stable_hash(
            {
                "provider": self.provider_id,
                "symbols": request.symbols,
                "interval": request.interval,
                "start": request.start_utc,
                "end": request.end_utc,
                "feed": "iex",
                "adjustment": params["adjustment"],
            }
        )[:24]
        return RawBarBatch(
            request_id=request_id,
            provider_id=self.provider_id,
            feed="iex",
            frame=frame.reset_index(drop=True),
            metadata={
                "feed": "iex",
                "page_count_unknown": True,
                "credentials_source": "environment",
            },
        )

    def _request_with_retries(
        self, client: httpx.Client, headers: dict[str, str], params: dict[str, Any]
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = client.get(self.endpoint, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise DataUnavailableError("Alpaca response root is not an object")
                return payload
            except (httpx.HTTPError, ValueError, DataUnavailableError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise DataUnavailableError(
            f"Alpaca request failed after {self.max_retries} attempts: {type(last_error).__name__}"
        ) from last_error
