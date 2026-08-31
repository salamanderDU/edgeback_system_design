from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from edgeback.calendar import XNYSCalendar
from edgeback.data.fixtures import fixture_capabilities, generate_fixture_bars
from edgeback.data.repository import DataRepository
from edgeback.data.schema import bars_to_frame
from edgeback.data.validation import validate_bars
from edgeback.domain import ValidationStatus


def test_fixture_validates_full_sessions() -> None:
    bars = generate_fixture_bars(symbols=("AAA", "BBB"))
    report = validate_bars(
        bars_to_frame(bars),
        calendar=XNYSCalendar(),
        minimum_session_completeness_pct=100.0,
        missing_session_policy="fail_dataset",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    assert report.status is ValidationStatus.PASS
    assert report.row_count == 2 * 3 * 78


def test_validation_rejects_duplicates_invalid_ohlc_and_mixed_feed() -> None:
    frame = bars_to_frame(generate_fixture_bars(symbols=("AAA",), session_count=1))
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True).sort_values(
        ["bar_end_utc", "symbol"], kind="stable"
    )
    assert validate_bars(duplicate).status is ValidationStatus.FAIL

    invalid = frame.copy()
    invalid.loc[0, "high"] = invalid.loc[0, "low"] - 1
    assert validate_bars(invalid).status is ValidationStatus.FAIL

    mixed = frame.copy()
    mixed.loc[0, "source_feed"] = "other"
    assert validate_bars(mixed).status is ValidationStatus.FAIL


def test_validation_reports_missing_session_without_forward_fill() -> None:
    frame = bars_to_frame(generate_fixture_bars(symbols=("AAA",), session_count=1)).iloc[:-5]
    report = validate_bars(
        frame,
        calendar=XNYSCalendar(),
        minimum_session_completeness_pct=98.0,
        missing_session_policy="fail_session",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    assert report.status is ValidationStatus.PASS_WITH_WARNINGS
    assert report.excluded_sessions
    assert len(frame) == 73


def test_repository_round_trip_and_checksum(tmp_path: Path) -> None:
    bars = generate_fixture_bars(symbols=("AAA",), session_count=2)
    repository = DataRepository(tmp_path / "data")
    manifest = repository.ingest(
        bars,
        calendar=XNYSCalendar(),
        capabilities=fixture_capabilities(),
        minimum_session_completeness_pct=100.0,
        missing_session_policy="fail_dataset",
    )
    loaded = repository.load_bars(manifest.dataset_id)
    assert [(bar.symbol, bar.bar_start_utc) for bar in loaded] == [
        (bar.symbol, bar.bar_start_utc) for bar in bars
    ]
    assert [bar.close for bar in loaded] == pytest.approx([bar.close for bar in bars])
    assert repository.load_manifest(manifest.dataset_id).aggregate_hash == manifest.aggregate_hash
