from datetime import UTC, datetime

import pandas as pd

from edgeback.data.schema import validate_dataframe


def create_valid_base_df() -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "provider_symbol": ["AAPL", "AAPL"],
            "interval_seconds": [300, 300],
            "bar_start_utc": [
                datetime(2025, 1, 1, 14, 30, tzinfo=UTC),
                datetime(2025, 1, 1, 14, 35, tzinfo=UTC),
            ],
            "bar_end_utc": [
                datetime(2025, 1, 1, 14, 35, tzinfo=UTC),
                datetime(2025, 1, 1, 14, 40, tzinfo=UTC),
            ],
            "session_date": [datetime(2025, 1, 1).date(), datetime(2025, 1, 1).date()],
            "session_type": ["regular", "regular"],
            "open": [100.0, 101.0],
            "high": [105.0, 102.0],
            "low": [99.0, 100.0],
            "close": [101.0, 100.5],
            "volume": [1000, 500],
            "vwap": [100.5, 101.0],
            "trade_count": [10, 5],
            "is_complete": [True, True],
            "source_provider": ["yahoofinance", "yahoofinance"],
            "source_feed": ["yahoofinance-feed", "yahoofinance-feed"],
            "adjustment_mode": ["split_adjusted", "split_adjusted"],
            "ingested_at_utc": [
                datetime(2025, 1, 1, 15, 0, tzinfo=UTC),
                datetime(2025, 1, 1, 15, 0, tzinfo=UTC),
            ],
        }
    )

    # Must represent these column components accurately
    # Pydantic / Pandas requires these tz tzinfo sets
    for c in ["bar_start_utc", "bar_end_utc", "ingested_at_utc"]:
        df[c] = pd.to_datetime(df[c])

    return df


def test_validation_clean_data() -> None:
    df = create_valid_base_df()
    report = validate_dataframe(df)
    assert report.is_valid is True
    assert len(report.issues) == 0


def test_validation_naive_tz() -> None:
    df = create_valid_base_df()
    # Strip timezone
    df["bar_start_utc"] = df["bar_start_utc"].dt.tz_localize(None)

    report = validate_dataframe(df)
    assert report.is_valid is False
    assert any(i.code == "INVALID_DATETIME_TYPE" for i in report.issues)


def test_validation_invalid_ohlc() -> None:
    df = create_valid_base_df()
    # High is less than open
    df.loc[0, "high"] = 50.0

    report = validate_dataframe(df)
    assert report.is_valid is False
    assert any(i.code == "INVALID_OPEN" for i in report.issues)
    assert any(i.code == "INVALID_CLOSE" for i in report.issues)


def test_validation_duplicate_bars() -> None:
    df = create_valid_base_df()

    # Make identically overlapping bars
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)

    report = validate_dataframe(df)
    assert report.is_valid is False
    assert any(i.code == "DUPLICATE_BARS" for i in report.issues)


def test_validation_missing_cols() -> None:
    df = create_valid_base_df()
    del df["volume"]

    report = validate_dataframe(df)
    assert report.is_valid is False
    assert any(i.code == "MISSING_COLUMNS" for i in report.issues)
