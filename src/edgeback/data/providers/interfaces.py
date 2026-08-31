from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd
from pydantic import Field, field_validator

from edgeback.domain.common import DomainModel, UTCModel


class ProviderCapabilities(DomainModel):
    provider_id: str
    feeds: tuple[str, ...]
    intervals: tuple[str, ...]
    earliest_history: str | None = None
    latest_data_delay_minutes: int | None = Field(default=None, ge=0)
    rate_limit_per_minute: int | None = Field(default=None, ge=0)
    limitations: tuple[str, ...] = ()


class ProviderSymbol(DomainModel):
    canonical_symbol: str
    provider_symbol: str


class BarRequest(UTCModel):
    symbols: tuple[str, ...]
    interval: str
    start_utc: datetime
    end_utc: datetime
    feed: str
    include_extended_hours: bool = False
    adjustment_mode: str = "split_adjusted"

    @field_validator("start_utc", "end_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)


class RawBarBatch(DomainModel):
    request_id: str
    provider_id: str
    feed: str
    frame: object
    metadata: dict[str, object] = Field(default_factory=dict)

    def dataframe(self) -> pd.DataFrame:
        if not isinstance(self.frame, pd.DataFrame):
            raise TypeError("RawBarBatch.frame is not a pandas DataFrame")
        return self.frame.copy(deep=True)


class MarketDataProvider(Protocol):
    provider_id: str

    def describe_capabilities(self) -> ProviderCapabilities: ...

    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol: ...

    def fetch_bars(self, request: BarRequest) -> RawBarBatch: ...
