from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class StrategyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    version: str
    name: str
    description: str
    scope: Literal["per_symbol", "portfolio"] = "per_symbol"
    markets: tuple[str, ...] = ("US_EQUITY", "US_ETF")
    timeframes: tuple[str, ...] = ("1m", "5m", "15m")
    directions: tuple[str, ...] = ("long", "short")
    required_fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")
    warmup_bars: int = Field(default=0, ge=0)
    previous_sessions_required: int = Field(default=0, ge=0)
    research_status: Literal["hypothesis", "experimental", "validated_for_dataset"] = "hypothesis"
    known_limitations: tuple[str, ...] = ()
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
