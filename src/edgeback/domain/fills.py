from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from edgeback.domain.common import UTCModel
from edgeback.domain.enums import Side


class Fill(UTCModel):
    fill_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    intent_id: int | None = Field(default=None, gt=0)
    parent_order_id: int | None = Field(default=None, gt=0)
    symbol: str
    side: Side
    quantity: int = Field(gt=0)
    timestamp_utc: datetime
    base_price: float = Field(gt=0)
    spread_cost_usd: float = Field(ge=0)
    slippage_cost_usd: float = Field(ge=0)
    commission_usd: float = Field(ge=0)
    effective_price: float = Field(gt=0)
    reason_code: str
    model_ids: dict[str, str] = Field(default_factory=dict)
    tags: tuple[str, ...] = ()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)

    @property
    def total_cost_usd(self) -> float:
        return self.spread_cost_usd + self.slippage_cost_usd + self.commission_usd

    def to_record(self) -> dict[str, Any]:
        return {**self.model_dump(mode="python"), "total_cost_usd": self.total_cost_usd}
