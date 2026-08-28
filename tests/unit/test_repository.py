from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from edgeback.data.manifest import DatasetManifest, DatasetStats, ProviderCapabilitySnapshot
from edgeback.data.repository import ParquetRepository
from edgeback.data.schema import DataValidationReport


@pytest.fixture
def temp_repo(tmp_path: Path) -> ParquetRepository:
    return ParquetRepository(data_dir=tmp_path)


def create_sample_df() -> pd.DataFrame:
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
            "source_provider": ["test_prov", "test_prov"],
            "source_feed": ["test_feed", "test_feed"],
            "adjustment_mode": ["split_adjusted", "split_adjusted"],
            "ingested_at_utc": [
                datetime(2025, 1, 1, 15, 0, tzinfo=UTC),
                datetime(2025, 1, 1, 15, 0, tzinfo=UTC),
            ],
        }
    )

    # Must enforce pandas tz bounds cleanly
    for c in ["bar_start_utc", "bar_end_utc", "ingested_at_utc"]:
        df[c] = pd.to_datetime(df[c])
    return df


def test_parquet_repository_write_read_partition(temp_repo: ParquetRepository) -> None:
    df = create_sample_df()

    # Write Partition
    partition_info = temp_repo.write_partition(
        df=df,
        provider="test_prov",
        feed="test_feed",
        interval=300,
        symbol="AAPL",
        year=2025,
        month=1,
    )

    assert partition_info.row_count == 2
    assert partition_info.path.startswith("canonical/bars/provider=test_prov")
    assert partition_info.checksum != ""

    # Create a mock manifest linking it
    manifest = DatasetManifest(
        dataset_id="test_dataset_aapl",
        provider="test_prov",
        source_feed="test_feed",
        provider_capabilities=ProviderCapabilitySnapshot(
            provider_id="test_prov",
            interval_seconds=[300],
            supports_pre_market=False,
            supports_post_market=False,
        ),
        symbols=["AAPL"],
        provider_symbols=["AAPL"],
        interval_seconds=300,
        requested_start_utc=datetime(2025, 1, 1, tzinfo=UTC),
        requested_end_utc=datetime(2025, 2, 1, tzinfo=UTC),
        session_types_included=["regular"],
        exchange_calendar_id="XNYS",
        adjustment_mode="split_adjusted",
        stats=DatasetStats(row_count=2, missing_bars=0, duplicate_bars=0, invalid_bars=0),
        validation_report=DataValidationReport(),
        partitions=[partition_info],
        aggregate_hash=partition_info.checksum,  # Simple placeholder
        ingested_at_utc=datetime.now(UTC),
    )

    temp_repo.write_manifest(manifest)

    loaded_manifest = temp_repo.get_manifest("test_dataset_aapl")
    assert loaded_manifest is not None
    assert loaded_manifest.dataset_id == "test_dataset_aapl"

    # Check Read back
    result_df = temp_repo.read_dataset("test_dataset_aapl")
    assert result_df is not None
    assert len(result_df) == 2
    assert result_df.iloc[0]["symbol"] == "AAPL"


def test_parquet_repository_empty_dataframe(temp_repo: ParquetRepository) -> None:
    df = pd.DataFrame()
    with pytest.raises(ValueError, match="Cannot write empty dataframe"):
        temp_repo.write_partition(
            df=df, provider="p", feed="f", interval=60, symbol="SYM", year=2025, month=1
        )
