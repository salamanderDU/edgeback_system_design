from __future__ import annotations

from datetime import timedelta

import pandas as pd

from edgeback.data.providers.interfaces import (
    BarRequest,
    ProviderCapabilities,
    ProviderSymbol,
    RawBarBatch,
)
from edgeback.errors import DataUnavailableError
from edgeback.utils import stable_hash


class YFinanceProvider:
    provider_id = "yfinance"

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            feeds=("yahoo",),
            intervals=("1m", "5m", "15m"),
            earliest_history="Provider-dependent; intraday requests are limited to recent history",
            limitations=(
                "Unofficial Yahoo adapter intended for research/personal use subject to provider terms.",
                "Intraday lookback is limited and provider behavior can change.",
                "OHLCV lacks bid/ask quotes and may have adjustment ambiguities.",
            ),
        )

    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol:
        canonical = canonical_symbol.strip().upper()
        return ProviderSymbol(
            canonical_symbol=canonical,
            provider_symbol=canonical.replace(".", "-"),
        )

    def fetch_bars(self, request: BarRequest) -> RawBarBatch:
        if request.feed.lower() != "yahoo":
            raise DataUnavailableError("YFinanceProvider only supports feed=yahoo")
        if request.end_utc - request.start_utc > timedelta(days=60):
            raise DataUnavailableError(
                "Requested yfinance intraday range exceeds the documented recent-history window"
            )
        try:
            import yfinance as yf
        except ImportError as exc:
            raise DataUnavailableError(
                "yfinance is not installed; install EdgeBack project dependencies"
            ) from exc

        provider_symbols = [self.resolve_symbol(symbol).provider_symbol for symbol in request.symbols]
        auto_adjust = request.adjustment_mode == "all_adjusted"
        try:
            raw = yf.download(
                tickers=provider_symbols,
                start=request.start_utc,
                end=request.end_utc,
                interval=request.interval,
                auto_adjust=auto_adjust,
                back_adjust=False,
                actions=False,
                repair=False,
                prepost=request.include_extended_hours,
                progress=False,
                threads=False,
                group_by="ticker",
                timeout=30,
            )
        except Exception as exc:
            raise DataUnavailableError(f"yfinance request failed: {type(exc).__name__}: {exc}") from exc
        if raw is None or raw.empty:
            raise DataUnavailableError("yfinance returned no bars")
        frame = self._flatten(raw, request.symbols, provider_symbols)
        request_id = stable_hash(
            {
                "provider": self.provider_id,
                "symbols": provider_symbols,
                "interval": request.interval,
                "start": request.start_utc,
                "end": request.end_utc,
                "prepost": request.include_extended_hours,
                "auto_adjust": auto_adjust,
            }
        )[:24]
        return RawBarBatch(
            request_id=request_id,
            provider_id=self.provider_id,
            feed="yahoo",
            frame=frame,
            metadata={
                "provider_symbols": provider_symbols,
                "auto_adjust": auto_adjust,
                "adjustment_request": request.adjustment_mode,
                "explicit_arguments": True,
            },
        )

    @staticmethod
    def _flatten(
        raw: pd.DataFrame, canonical_symbols: tuple[str, ...], provider_symbols: list[str]
    ) -> pd.DataFrame:
        output: list[pd.DataFrame] = []
        if isinstance(raw.columns, pd.MultiIndex):
            top = set(map(str, raw.columns.get_level_values(0)))
            for canonical, provider_symbol in zip(canonical_symbols, provider_symbols, strict=True):
                if provider_symbol in top:
                    selected = raw[provider_symbol].copy()
                else:
                    # Some yfinance versions return field first and ticker second.
                    selected = raw.xs(provider_symbol, axis=1, level=-1).copy()
                selected["symbol"] = canonical
                selected["provider_symbol"] = provider_symbol
                output.append(selected.reset_index())
        else:
            selected = raw.copy()
            selected["symbol"] = canonical_symbols[0]
            selected["provider_symbol"] = provider_symbols[0]
            output.append(selected.reset_index())
        result = pd.concat(output, ignore_index=True)
        result.columns = [str(column).strip().lower().replace(" ", "_") for column in result.columns]
        timestamp = next(
            (name for name in ("datetime", "date", "timestamp") if name in result.columns), None
        )
        if timestamp is None:
            raise DataUnavailableError("Could not identify yfinance timestamp column")
        result = result.rename(columns={timestamp: "timestamp"})
        return result.rename(
            columns={
                "adj_close": "adjusted_close",
                "stock_splits": "stock_splits",
            }
        )
