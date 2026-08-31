from edgeback.data.providers.alpaca_provider import AlpacaIEXProvider
from edgeback.data.providers.interfaces import (
    BarRequest,
    MarketDataProvider,
    ProviderCapabilities,
    ProviderSymbol,
    RawBarBatch,
)
from edgeback.data.providers.local_file_provider import LocalFileProvider
from edgeback.data.providers.yfinance_provider import YFinanceProvider


def provider_for(name: str) -> MarketDataProvider:
    normalized = name.strip().lower()
    if normalized == "yfinance":
        return YFinanceProvider()
    if normalized == "alpaca":
        return AlpacaIEXProvider()
    raise ValueError(f"No downloadable provider named {name!r}")


__all__ = [
    "AlpacaIEXProvider",
    "BarRequest",
    "LocalFileProvider",
    "MarketDataProvider",
    "ProviderCapabilities",
    "ProviderSymbol",
    "RawBarBatch",
    "YFinanceProvider",
    "provider_for",
]
