from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from edgeback.data.providers.local_file_provider import LocalFileProvider
from edgeback.errors import DataValidationError


def test_local_csv_requires_explicit_timezone(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    pd.DataFrame(
        {
            "timestamp": ["2025-01-06 09:30:00"],
            "open": [100],
            "high": [101],
            "low": [99],
            "close": [100.5],
            "volume": [1000],
        }
    ).to_csv(path, index=False)
    provider = LocalFileProvider()
    with pytest.raises(DataValidationError):
        provider.import_file(
            path,
            symbol="AAA",
            interval_seconds=300,
            timestamp_column="timestamp",
            timestamp_semantics="bar_start",
            source_timezone="",
            feed="paid_test",
            adjustment_mode="raw",
        )
    bars = provider.import_file(
        path,
        symbol="AAA",
        interval_seconds=300,
        timestamp_column="timestamp",
        timestamp_semantics="bar_start",
        source_timezone="America/New_York",
        feed="paid_test",
        adjustment_mode="raw",
    )
    assert bars[0].bar_start_utc.isoformat() == "2025-01-06T14:30:00+00:00"
