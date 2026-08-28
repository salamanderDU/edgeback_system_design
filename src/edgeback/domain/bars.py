from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from edgeback.config.models import BaseStrictModel


class Bar(BaseStrictModel):
    """
    Canonical Bar representing OHLCV data for an interval.
    Matches schemas/bar.schema.json.
    """

    symbol: str = Field(pattern="^[A-Z0-9.\\-]+$")
    provider_symbol: str = Field(min_length=1)
    interval_seconds: int = Field(gt=0)

    # Needs to be aware
    bar_start_utc: datetime
    bar_end_utc: datetime

    session_date: date
    session_type: Literal["regular", "pre", "post", "overnight"]

    open: float = Field(gt=0.0)
    high: float = Field(gt=0.0)
    low: float = Field(gt=0.0)
    close: float = Field(gt=0.0)
    volume: int = Field(ge=0)

    vwap: float | None = Field(default=None, gt=0.0)
    trade_count: int | None = Field(default=None, ge=0)

    is_complete: bool
    source_provider: str = Field(min_length=1)
    source_feed: str = Field(min_length=1)
    adjustment_mode: Literal["raw", "split_adjusted", "provider_adjusted"]
    ingested_at_utc: datetime

    @model_validator(mode="after")
    def validate_ohlc_and_times(self: "Bar") -> "Bar":
        # Check OHLC logical bounds
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"Open {self.open} must be between Low {self.low} and High {self.high}"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"Close {self.close} must be between Low {self.low} and High {self.high}"
            )

        # Timezone checking
        stz = self.bar_start_utc.tzinfo
        if stz is None or stz.utcoffset(self.bar_start_utc) is None:
            raise ValueError("bar_start_utc must be timezone-aware (UTC)")

        etz = self.bar_end_utc.tzinfo
        if etz is None or etz.utcoffset(self.bar_end_utc) is None:
            raise ValueError("bar_end_utc must be timezone-aware (UTC)")

        itz = self.ingested_at_utc.tzinfo
        if itz is None or itz.utcoffset(self.ingested_at_utc) is None:
            raise ValueError("ingested_at_utc must be timezone-aware (UTC)")

        if self.bar_start_utc >= self.bar_end_utc:
            raise ValueError("bar_start_utc must be strictly before bar_end_utc")

        return self
