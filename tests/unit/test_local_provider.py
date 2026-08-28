from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from edgeback.data.providers.interfaces import BarRequest
from edgeback.data.providers.local import LocalFileProvider, LocalImportConfig
from edgeback.data.schema import validate_dataframe


@pytest.fixture
def sample_csv(tmp_path: Path) -> str:
    # Create sample CSV with naive datetime
    df = pd.DataFrame(
        {
            "timestamp": ["2023-01-03 09:30:00", "2023-01-03 09:35:00"],
            "open": [10.0, 10.5],
            "high": [11.0, 10.7],
            "low": [9.5, 10.2],
            "close": [10.5, 10.3],
            "volume": [1000, 1500],
        }
    )

    file_path = tmp_path / "test_data.csv"
    df.to_csv(file_path, index=False)
    return str(file_path)


def test_local_file_provider_csv(sample_csv: str) -> None:
    config = LocalImportConfig(
        file_path=sample_csv,
        symbol="TEST",
        interval_seconds=300,
        timezone="America/New_York",
        timestamp_semantics="bar_start",
        adjustment_mode="raw",
        source_feed="local_csv",
    )

    provider = LocalFileProvider(config)

    request = BarRequest(
        symbols=["TEST"],
        interval_seconds=300,
        start_utc=datetime(2023, 1, 3, 14, 0, tzinfo=UTC),
        end_utc=datetime(2023, 1, 4, tzinfo=UTC),
    )

    batch = provider.fetch_bars(request)
    df = batch.data

    assert len(df) == 2
    assert df.iloc[0]["symbol"] == "TEST"

    expected_start = datetime(2023, 1, 3, 9, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(
        UTC
    )
    assert df.iloc[0]["bar_start_utc"] == pd.Timestamp(expected_start)
    assert df.iloc[0]["volume"] == 1000

    # Should validate cleanly
    report = validate_dataframe(df)
    assert report.is_valid is True


def test_local_file_provider_unknown_timezone(sample_csv: str) -> None:
    config = LocalImportConfig(
        file_path=sample_csv,
        symbol="TEST",
        interval_seconds=300,
        timezone="Invalid/Timezone",
        timestamp_semantics="bar_start",
        adjustment_mode="raw",
        source_feed="local_csv",
    )

    provider = LocalFileProvider(config)

    request = BarRequest(
        symbols=["TEST"],
        interval_seconds=300,
        start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        end_utc=datetime(2023, 1, 5, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="Unknown timezone"):
        provider.fetch_bars(request)
