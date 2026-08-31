from datetime import UTC, date, datetime

from edgeback.calendar import XNYSCalendar


def test_xnys_normal_holiday_dst_and_early_close() -> None:
    calendar = XNYSCalendar()
    summer = calendar.session(date(2026, 8, 28))
    winter = calendar.session(date(2026, 1, 5))
    early = calendar.session(date(2026, 11, 27))

    assert summer.open_utc.hour == 13
    assert winter.open_utc.hour == 14
    assert early.close_utc == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert early.is_early_close
    assert not calendar.is_session(date(2026, 7, 3))


def test_expected_bars_do_not_cross_close() -> None:
    calendar = XNYSCalendar()
    starts = calendar.expected_bar_starts(date(2026, 11, 27), 300)
    assert len(starts) == 42
    assert starts[0] == datetime(2026, 11, 27, 14, 30, tzinfo=UTC)
    assert starts[-1] == datetime(2026, 11, 27, 17, 55, tzinfo=UTC)
