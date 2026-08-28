from datetime import date

from edgeback.calendar.xnys import XNYSCalendar


def test_xnys_normal_day() -> None:
    cal = XNYSCalendar()

    # 2024-01-09 is a Tuesday, normal day
    d = date(2024, 1, 9)
    assert cal.is_session(d) is True

    # Open should be 09:30 America/New_York -> 14:30 UTC
    open_time = cal.session_open(d)
    assert open_time.hour == 14
    assert open_time.minute == 30
    assert open_time.tzinfo is not None

    # Close should be 16:00 America/New_York -> 21:00 UTC
    close_time = cal.session_close(d)
    assert close_time.hour == 21
    assert close_time.minute == 0

    assert cal.is_early_close(d) is False


def test_xnys_holiday() -> None:
    cal = XNYSCalendar()

    # 2024-01-01 is New Year's Day, holiday
    d = date(2024, 1, 1)
    assert cal.is_session(d) is False


def test_xnys_early_close() -> None:
    cal = XNYSCalendar()

    # 2024-07-03 (day before Independence Day) is an early close at 13:00 NY -> 17:00 UTC
    d = date(2024, 7, 3)
    assert cal.is_session(d) is True
    assert cal.is_early_close(d) is True

    close_time = cal.session_close(d)
    assert close_time.hour == 17
    assert close_time.minute == 0


def test_xnys_daylight_saving() -> None:
    cal = XNYSCalendar()

    # 2024-06-03 (Summer time, EDT)
    d_summer = date(2024, 6, 3)
    # Open: 09:30 EDT -> 13:30 UTC
    open_summer = cal.session_open(d_summer)
    assert open_summer.hour == 13

    # 2024-12-03 (Winter time, EST)
    d_winter = date(2024, 12, 3)
    # Open: 09:30 EST -> 14:30 UTC
    open_winter = cal.session_open(d_winter)
    assert open_winter.hour == 14
