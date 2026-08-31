from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from edgeback.domain.common import UTCModel
from edgeback.domain.enums import PositionSide


class Position(UTCModel):
    symbol: str
    quantity: int
    average_price: float = Field(ge=0)
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    last_price: float = Field(default=0.0, ge=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def side(self) -> PositionSide | None:
        if self.quantity > 0:
            return PositionSide.LONG
        if self.quantity < 0:
            return PositionSide.SHORT
        return None


class PortfolioSnapshot(UTCModel):
    timestamp_utc: datetime
    cash_usd: float
    equity_usd: float
    gross_exposure_usd: float = Field(ge=0)
    net_exposure_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_costs_usd: float = Field(ge=0)
    positions: tuple[Position, ...] = ()

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)
