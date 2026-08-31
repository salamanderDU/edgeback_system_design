from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from edgeback.domain.common import UTCModel
from edgeback.domain.enums import IntentType, OrderStatus, OrderType, Side, TimeInForce


class OrderIntent(UTCModel):
    intent_id: int = Field(gt=0)
    strategy_id: str
    strategy_version: str
    symbol: str
    side: Side
    intent_type: IntentType = IntentType.ENTRY
    order_type: OrderType = OrderType.MARKET
    signal_time_utc: datetime
    limit_price: float | None = Field(default=None, gt=0)
    stop_trigger_price: float | None = Field(default=None, gt=0)
    requested_quantity: int | None = Field(default=None, gt=0)
    sizing_model: str | None = None
    entry_reference_price: float | None = Field(default=None, gt=0)
    stop_loss_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    expires_at_utc: datetime | None = None
    priority: int = 0
    reason_code: str
    rationale: str = ""
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    protective_exit: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("signal_time_utc", "expires_at_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return cls.ensure_aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_price_fields(self) -> Self:
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit order intent requires limit_price")
        if self.order_type is OrderType.STOP and self.stop_trigger_price is None:
            raise ValueError("stop order intent requires stop_trigger_price")
        if self.intent_type is IntentType.ENTRY and self.stop_loss_price is not None:
            reference = self.entry_reference_price
            if reference is not None:
                if self.side is Side.BUY and self.stop_loss_price >= reference:
                    raise ValueError("long stop must be below entry reference")
                if self.side is Side.SELL and self.stop_loss_price <= reference:
                    raise ValueError("short stop must be above entry reference")
        return self


class Order(UTCModel):
    order_id: int = Field(gt=0)
    intent_id: int | None = Field(default=None, gt=0)
    parent_order_id: int | None = Field(default=None, gt=0)
    strategy_id: str
    strategy_version: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: int = Field(gt=0)
    status: OrderStatus = OrderStatus.ACCEPTED
    created_at_utc: datetime
    eligible_from_utc: datetime
    expires_at_utc: datetime | None = None
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    bracket_stop_price: float | None = Field(default=None, gt=0)
    bracket_target_price: float | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.DAY
    priority: int = 0
    creation_sequence: int = Field(gt=0)
    reduce_only: bool = False
    reason_code: str = "ACCEPTED"
    estimated_risk_usd: float | None = Field(default=None, ge=0)
    tags: tuple[str, ...] = ()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("created_at_utc", "eligible_from_utc", "expires_at_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return cls.ensure_aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.eligible_from_utc < self.created_at_utc:
            raise ValueError("eligible_from_utc cannot precede creation")
        if self.expires_at_utc is not None and self.expires_at_utc < self.eligible_from_utc:
            raise ValueError("order expiry cannot precede eligibility")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("stop order requires stop_price")
        return self


class OrderEvent(UTCModel):
    event_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    timestamp_utc: datetime
    previous_status: OrderStatus | None = None
    status: OrderStatus
    reason_code: str
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)
