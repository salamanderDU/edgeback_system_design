from datetime import date, datetime

import pandas_market_calendars as mcal

from edgeback.calendar.interfaces import TradingCalendar


class XNYSCalendar(TradingCalendar):
    """
    Implementation of the TradingCalendar protocol using pandas_market_calendars
    for the XNYS (New York Stock Exchange).
    """

    def __init__(self) -> None:
        self._cal = mcal.get_calendar("XNYS")

    @property
    def name(self) -> str:
        return "XNYS"

    @property
    def timezone(self) -> str:
        # In newer Python zoneinfo, it's .key
        return getattr(self._cal.tz, "key", str(self._cal.tz))

    def is_session(self, dt_date: date) -> bool:
        # Check if the date is in the valid trading days.
        # schedule is a dataframe. We can fetch schedule for that day to see if it exists.
        start = dt_date.strftime("%Y-%m-%d")
        end = dt_date.strftime("%Y-%m-%d")
        schedule = self._cal.schedule(start_date=start, end_date=end)
        return not schedule.empty

    def session_open(self, dt_date: date) -> datetime:
        start = dt_date.strftime("%Y-%m-%d")
        schedule = self._cal.schedule(start_date=start, end_date=start)
        if schedule.empty:
            raise ValueError(f"{dt_date} is not a valid trading session.")
        # p_m_c returns timezone aware pandas Timestamp (UTC)
        result: datetime = schedule.iloc[0]["market_open"].to_pydatetime()
        return result

    def session_close(self, dt_date: date) -> datetime:
        start = dt_date.strftime("%Y-%m-%d")
        schedule = self._cal.schedule(start_date=start, end_date=start)
        if schedule.empty:
            raise ValueError(f"{dt_date} is not a valid trading session.")
        result: datetime = schedule.iloc[0]["market_close"].to_pydatetime()
        return result

    def is_early_close(self, dt_date: date) -> bool:
        """Returns True if the given session date has an early close."""
        start = dt_date.strftime("%Y-%m-%d")
        schedule = self._cal.schedule(start_date=start, end_date=start)
        if schedule.empty:
            return False

        # If market close time in local timezone is earlier than regular (16:00)
        # mcal `early_closes` property returns a list of early close times. The schedule handles it.
        # Check standard close vs actual close.
        m_close_utc = schedule.iloc[0]["market_close"]

        # We can extract the actual local time
        m_close_local = m_close_utc.tz_convert(self.timezone)
        result: bool = m_close_local.hour < 16
        return result
