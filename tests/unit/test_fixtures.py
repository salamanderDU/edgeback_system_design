import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from edgeback.data.schema import validate_dataframe
from tests.fixtures.synthetic import (
    generate_ambiguous_brackets_fixtures,
    generate_early_close_fixtures,
    generate_gaps_and_missing_bars_fixtures,
    generate_standard_regular_session_fixtures,
)


def test_regular_session_fixture_valid() -> None:
    df = generate_standard_regular_session_fixtures()
    # It must have exactly 78 bars
    assert len(df) == 78

    # Must pass validation safely
    report = validate_dataframe(df)
    assert report.is_valid


def test_missing_bars_fixture_valid() -> None:
    df = generate_gaps_and_missing_bars_fixtures()
    # 78 - 6
    assert len(df) == 72
    report = validate_dataframe(df)
    assert report.is_valid


def test_ambiguous_brackets_fixture_valid() -> None:
    df = generate_ambiguous_brackets_fixtures()
    assert len(df) == 78
    report = validate_dataframe(df)
    assert report.is_valid


def test_early_close_fixture_valid() -> None:
    df = generate_early_close_fixtures()
    # July 3rd bounds out to exactly 1:00 PM close (210 mins or 42 bars of 5 mins)
    assert len(df) == 42
    report = validate_dataframe(df)
    assert report.is_valid
