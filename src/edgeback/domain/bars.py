from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from edgeback.domain.common import UTCModel
from edgeback.domain.enums import SessionType


class Bar(UTCModel):
    symbol: str
    provider_symbol: str
    interval_seconds: int = Field(gt=0)
    bar_start_utc: datetime
    bar_end_utc: datetime
    session_date: date
    session_type: SessionType = SessionType.REGULAR
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)
    vwap: float | None = Field(default=None, gt=0)
    trade_count: int | None = Field(default=None, ge=0)
    is_complete: bool = True
    source_provider: str
    source_feed: str
    adjustment_mode: str
    ingested_at_utc: datetime

    @field_validator("symbol", "provider_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol must not be empty")
        return value

    @field_validator("bar_start_utc", "bar_end_utc", "ingested_at_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)

    @field_validator("open", "high", "low", "close", "vwap")
    @classmethod
    def finite_prices(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("price must be finite")
        return value

    @model_validator(mode="after")
    def validate_bar(self) -> Self:
        if self.bar_end_utc <= self.bar_start_utc:
            raise ValueError("bar_end_utc must be after bar_start_utc")
        actual = int((self.bar_end_utc - self.bar_start_utc).total_seconds())
        if actual != self.interval_seconds:
            raise ValueError("bar duration does not equal interval_seconds")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be at least max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be at most min(open, close)")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        return self

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
