from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import exchange_calendars as xcals

from edgeback.calendar.interfaces import TradingSession
from edgeback.errors import DataValidationError


class XNYSCalendar:
    calendar_id = "XNYS"
    timezone = "America/New_York"

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar("XNYS")

    @staticmethod
    def _key(value: date) -> str:
        return value.isoformat()

    def is_session(self, session_date: date) -> bool:
        return bool(self._calendar.is_session(self._key(session_date)))

    def session(self, session_date: date) -> TradingSession:
        if not self.is_session(session_date):
            raise DataValidationError(f"{session_date} is not an XNYS session")
        key = self._key(session_date)
        opened = self._calendar.session_open(key).to_pydatetime().astimezone(UTC)
        closed = self._calendar.session_close(key).to_pydatetime().astimezone(UTC)
        standard_seconds = int(timedelta(hours=6, minutes=30).total_seconds())
        return TradingSession(
            session_date=session_date,
            open_utc=opened,
            close_utc=closed,
            is_early_close=int((closed - opened).total_seconds()) < standard_seconds,
        )

    def sessions(self, start: date, end: date) -> tuple[TradingSession, ...]:
        labels = self._calendar.sessions_in_range(start.isoformat(), end.isoformat())
        return tuple(self.session(label.date()) for label in labels)

    def expected_bar_starts(
        self, session_date: date, interval_seconds: int
    ) -> tuple[datetime, ...]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        session = self.session(session_date)
        starts: list[datetime] = []
        cursor = session.open_utc
        step = timedelta(seconds=interval_seconds)
        while cursor + step <= session.close_utc:
            starts.append(cursor)
            cursor += step
        return tuple(starts)

    def session_for_timestamp(self, timestamp_utc: datetime) -> TradingSession | None:
        if timestamp_utc.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        candidate = timestamp_utc.astimezone(UTC).date()
        for offset in (0, -1, 1):
            day = candidate + timedelta(days=offset)
            if self.is_session(day):
                session = self.session(day)
                if session.open_utc <= timestamp_utc.astimezone(UTC) <= session.close_utc:
                    return session
        return None
