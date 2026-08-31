from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class UTCModel(DomainModel):
    @staticmethod
    def ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        converted = value.astimezone(UTC)
        if hasattr(converted, "to_pydatetime"):
            converted = converted.to_pydatetime()
        return converted


class FeatureSnapshot(DomainModel):
    values: dict[str, Any] = Field(default_factory=dict)
