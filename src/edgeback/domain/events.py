from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from edgeback.domain.common import UTCModel


class WarningEvent(UTCModel):
    warning_id: int = Field(gt=0)
    timestamp_utc: datetime
    code: str
    message: str
    symbol: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)


class EquityPoint(UTCModel):
    timestamp_utc: datetime
    session_date: str
    cash_usd: float
    equity_usd: float
    gross_exposure_usd: float
    net_exposure_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_costs_usd: float

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)
