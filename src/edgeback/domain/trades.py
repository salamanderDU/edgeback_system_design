from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from edgeback.domain.common import UTCModel
from edgeback.domain.enums import PositionSide


class Trade(UTCModel):
    trade_id: int = Field(gt=0)
    symbol: str
    side: PositionSide
    quantity: int = Field(gt=0)
    entry_fill_id: int = Field(gt=0)
    exit_fill_id: int = Field(gt=0)
    entry_order_id: int = Field(gt=0)
    exit_order_id: int = Field(gt=0)
    entry_time_utc: datetime
    exit_time_utc: datetime
    session_date: date
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    gross_pnl_usd: float
    costs_usd: float = Field(ge=0)
    net_pnl_usd: float
    holding_seconds: float = Field(ge=0)
    exit_reason: str
    tags: tuple[str, ...] = ()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("entry_time_utc", "exit_time_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)
