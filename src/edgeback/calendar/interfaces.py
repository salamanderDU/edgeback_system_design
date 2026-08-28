from datetime import date, datetime
from typing import Protocol


class TradingCalendar(Protocol):
    """
    Protocol defining how EdgeBack accesses calendar info.
    Must return timezone-aware UTC datetimes.
    """

    @property
    def name(self) -> str:
        """Standard calendar identifier, e.g. 'XNYS'"""
        ...

    @property
    def timezone(self) -> str:
        """The canonical timezone name for the exchange, e.g., 'America/New_York'"""
        ...

    def is_session(self, dt_date: date) -> bool:
        """Returns True if the given date is a trading session."""
        ...

    def session_open(self, dt_date: date) -> datetime:
        """Returns the regular session open time in UTC."""
        ...

    def session_close(self, dt_date: date) -> datetime:
        """Returns the regular session close time in UTC. Accounts for early closes."""
        ...

    def is_early_close(self, dt_date: date) -> bool:
        """Returns True if the given session date has an early close."""
        ...
