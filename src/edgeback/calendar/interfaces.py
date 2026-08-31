from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from pydantic import field_validator

from edgeback.domain.common import UTCModel


class TradingSession(UTCModel):
    session_date: date
    open_utc: datetime
    close_utc: datetime
    is_early_close: bool = False

    @field_validator("open_utc", "close_utc")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return cls.ensure_aware_utc(value)


class TradingCalendar(Protocol):
    calendar_id: str
    timezone: str

    def is_session(self, session_date: date) -> bool: ...

    def session(self, session_date: date) -> TradingSession: ...

    def sessions(self, start: date, end: date) -> tuple[TradingSession, ...]: ...

    def expected_bar_starts(self, session_date: date, interval_seconds: int) -> tuple[datetime, ...]: ...
