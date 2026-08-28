from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd


def dt(
    year: int, month: int, day: int, hour: int, minute: int, tz: str = "America/New_York"
) -> datetime:
    """Helper to create timezone aware datetimes using zoneinfo, matching standard logic."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz))


def generate_standard_regular_session_fixtures() -> pd.DataFrame:
    """
    Generate a simple standard session logic matching normal fills.
    Symbol: NORM
    Date: 2024-01-09 (Regular day)
    Interval: 5m (300s)
    """
    start = dt(2024, 1, 9, 9, 30)

    rows = []
    current_time = start

    price = 100.0
    for i in range(78):  # 78 bars in a regular US 390-minute session (9:30 to 16:00)
        # Shift a bit
        open_p = price
        high_p = price + 1.0
        low_p = price - 1.0
        close_p = price + 0.5

        start_utc = current_time.astimezone(UTC)

        # Next 5 minute
        end_utc = start_utc + pd.Timedelta(minutes=5)

        rows.append(
            {
                "symbol": "NORM",
                "provider_symbol": "NORM",
                "interval_seconds": 300,
                "bar_start_utc": start_utc,
                "bar_end_utc": end_utc,
                "session_date": current_time.date(),
                "session_type": "regular",
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 1000 + i * 10,
                "vwap": price,
                "trade_count": 100,
                "is_complete": True,
                "source_provider": "synthetic",
                "source_feed": "fixtures",
                "adjustment_mode": "split_adjusted",
                "ingested_at_utc": datetime(2024, 1, 9, 20, 0, tzinfo=UTC),
            }
        )

        # Prepare for next bar
        price = close_p
        current_time = current_time + pd.Timedelta(minutes=5)

    df = pd.DataFrame(rows)
    # Ensure correct pandas types handling
    df["bar_start_utc"] = pd.to_datetime(df["bar_start_utc"])
    df["bar_end_utc"] = pd.to_datetime(df["bar_end_utc"])
    df["ingested_at_utc"] = pd.to_datetime(df["ingested_at_utc"])

    return df


def generate_gaps_and_missing_bars_fixtures() -> pd.DataFrame:
    """
    Generate logic that has holes for 'missing bars' testing requirements.
    Symbol: GAPS
    Date: 2024-01-09
    Interval: 5m (300s)
    """
    regular = generate_standard_regular_session_fixtures()
    regular["symbol"] = "GAPS"
    regular["provider_symbol"] = "GAPS"

    # We remove bars indices 10 through 15 representing a 30m outage of quote volume
    regular = regular.drop(regular.index[10:16]).reset_index(drop=True)
    return regular


def generate_ambiguous_brackets_fixtures() -> pd.DataFrame:
    """
    Generate brackets where both target and stop might be hit in the same bar constraints.
    Symbol: AMBG
    Date: 2024-01-09
    Interval: 5m (300s)
    """
    df = generate_standard_regular_session_fixtures()
    df["symbol"] = "AMBG"
    df["provider_symbol"] = "AMBG"

    # 5th bar has enormous wide brackets
    open_val = float(str(df.loc[5, "open"]))
    df.loc[5, "high"] = open_val + 10.0
    df.loc[5, "low"] = open_val - 10.0
    df.loc[5, "close"] = open_val

    return df


def generate_early_close_fixtures() -> pd.DataFrame:
    """
    Generate early closure fixtures matching July 3rd constraints (early close at 13:00 NY)
    Symbol: ERLY
    Date: 2024-07-03
    Interval: 5m (300s)
    (9:30 to 13:00) is 210 minutes = 42 bars of 5 mins.
    """
    start = dt(2024, 7, 3, 9, 30)

    rows = []
    current_time = start

    price = 100.0
    for i in range(42):
        open_p = price
        high_p = price + 1.0
        low_p = price - 1.0
        close_p = price + 0.5

        start_utc = current_time.astimezone(UTC)
        end_utc = start_utc + pd.Timedelta(minutes=5)

        rows.append(
            {
                "symbol": "ERLY",
                "provider_symbol": "ERLY",
                "interval_seconds": 300,
                "bar_start_utc": start_utc,
                "bar_end_utc": end_utc,
                "session_date": current_time.date(),
                "session_type": "regular",
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 1000 + i * 10,
                "vwap": price,
                "trade_count": 100,
                "is_complete": True,
                "source_provider": "synthetic",
                "source_feed": "fixtures",
                "adjustment_mode": "split_adjusted",
                "ingested_at_utc": datetime(2024, 7, 3, 20, 0, tzinfo=UTC),
            }
        )

        price = close_p
        current_time = current_time + pd.Timedelta(minutes=5)

    df = pd.DataFrame(rows)
    df["bar_start_utc"] = pd.to_datetime(df["bar_start_utc"])
    df["bar_end_utc"] = pd.to_datetime(df["bar_end_utc"])
    df["ingested_at_utc"] = pd.to_datetime(df["ingested_at_utc"])

    return df
