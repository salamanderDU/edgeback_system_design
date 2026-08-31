from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from pydantic import Field

from edgeback.calendar import TradingCalendar
from edgeback.domain.common import DomainModel
from edgeback.domain.enums import ValidationStatus
from edgeback.data.schema import CANONICAL_BAR_COLUMNS


class ValidationIssue(DomainModel):
    code: str
    severity: str
    message: str
    row_count: int = Field(default=0, ge=0)
    context: dict[str, Any] = Field(default_factory=dict)


class DataValidationReport(DomainModel):
    status: ValidationStatus
    row_count: int = Field(ge=0)
    valid_row_count: int = Field(ge=0)
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()
    excluded_sessions: tuple[str, ...] = ()
    summary: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is not ValidationStatus.FAIL


def _timezone_aware(series: pd.Series) -> bool:
    try:
        dtype = series.dtype
        return isinstance(dtype, pd.DatetimeTZDtype)
    except (AttributeError, TypeError):
        return False


def validate_bars(
    frame: pd.DataFrame,
    *,
    calendar: TradingCalendar | None = None,
    minimum_session_completeness_pct: float = 0.0,
    missing_session_policy: str = "fail_session",
    allow_incomplete_latest_bar: bool = False,
    now: datetime | None = None,
) -> DataValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    excluded: list[str] = []
    row_count = len(frame)
    missing = sorted(set(CANONICAL_BAR_COLUMNS) - set(frame.columns))
    if missing:
        errors.append(
            ValidationIssue(
                code="MISSING_COLUMNS",
                severity="error",
                message=f"Missing canonical columns: {missing}",
                context={"columns": missing},
            )
        )
        return DataValidationReport(
            status=ValidationStatus.FAIL,
            row_count=row_count,
            valid_row_count=0,
            errors=tuple(errors),
        )
    if frame.empty:
        errors.append(
            ValidationIssue(code="EMPTY_DATASET", severity="error", message="Dataset is empty")
        )
        return DataValidationReport(
            status=ValidationStatus.FAIL,
            row_count=0,
            valid_row_count=0,
            errors=tuple(errors),
        )

    for column in ("bar_start_utc", "bar_end_utc", "ingested_at_utc"):
        if not _timezone_aware(frame[column]):
            errors.append(
                ValidationIssue(
                    code="TIMEZONE_NAIVE",
                    severity="error",
                    message=f"{column} must be timezone-aware",
                    row_count=len(frame),
                )
            )

    numeric_columns = ("open", "high", "low", "close", "volume")
    for column in numeric_columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        bad = int((~numeric.map(lambda value: math.isfinite(float(value)))).sum())
        if bad:
            errors.append(
                ValidationIssue(
                    code="NONFINITE_VALUE",
                    severity="error",
                    message=f"{column} contains non-finite values",
                    row_count=bad,
                    context={"column": column},
                )
            )

    invalid_price = (
        (frame["open"] <= 0)
        | (frame["high"] <= 0)
        | (frame["low"] <= 0)
        | (frame["close"] <= 0)
        | (frame["high"] < frame[["open", "close"]].max(axis=1))
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame["high"] < frame["low"])
    )
    if invalid_price.any():
        errors.append(
            ValidationIssue(
                code="INVALID_OHLC",
                severity="error",
                message="OHLC invariants failed",
                row_count=int(invalid_price.sum()),
            )
        )
    negative_volume = frame["volume"] < 0
    if negative_volume.any():
        errors.append(
            ValidationIssue(
                code="NEGATIVE_VOLUME",
                severity="error",
                message="Volume must be nonnegative",
                row_count=int(negative_volume.sum()),
            )
        )

    duplicate = frame.duplicated(["symbol", "interval_seconds", "bar_start_utc"], keep=False)
    if duplicate.any():
        errors.append(
            ValidationIssue(
                code="DUPLICATE_BAR",
                severity="error",
                message="Duplicate canonical bar keys found",
                row_count=int(duplicate.sum()),
            )
        )

    sorted_frame = frame.sort_values(["bar_end_utc", "symbol"], kind="stable")
    if not sorted_frame.index.equals(frame.index):
        errors.append(
            ValidationIssue(
                code="UNSORTED_BARS",
                severity="error",
                message="Bars must be sorted by bar_end_utc then symbol",
            )
        )

    duration = (frame["bar_end_utc"] - frame["bar_start_utc"]).dt.total_seconds()
    bad_duration = duration != frame["interval_seconds"]
    if bad_duration.any():
        errors.append(
            ValidationIssue(
                code="INVALID_DURATION",
                severity="error",
                message="Bar duration differs from interval_seconds",
                row_count=int(bad_duration.sum()),
            )
        )

    incomplete = ~frame["is_complete"].astype(bool)
    if incomplete.any():
        count = int(incomplete.sum())
        if allow_incomplete_latest_bar and count == 1 and bool(incomplete.iloc[-1]):
            warnings.append(
                ValidationIssue(
                    code="INCOMPLETE_LATEST_BAR",
                    severity="warning",
                    message="Latest incomplete bar must be excluded before simulation",
                    row_count=1,
                )
            )
        else:
            errors.append(
                ValidationIssue(
                    code="INCOMPLETE_BAR",
                    severity="error",
                    message="Incomplete bars cannot be simulated",
                    row_count=count,
                )
            )

    current = (now or datetime.now(UTC)).astimezone(UTC)
    if _timezone_aware(frame["bar_end_utc"]):
        future = frame["bar_end_utc"] > current
        if future.any():
            errors.append(
                ValidationIssue(
                    code="FUTURE_BAR",
                    severity="error",
                    message="Dataset contains bars ending in the future",
                    row_count=int(future.sum()),
                )
            )

    for symbol, group in frame.groupby("symbol", sort=True):
        for field, code in (
            ("source_provider", "MIXED_PROVIDER"),
            ("source_feed", "MIXED_FEED"),
            ("adjustment_mode", "MIXED_ADJUSTMENT"),
            ("interval_seconds", "MIXED_INTERVAL"),
        ):
            if group[field].nunique(dropna=False) != 1:
                errors.append(
                    ValidationIssue(
                        code=code,
                        severity="error",
                        message=f"{symbol} mixes {field} values",
                        row_count=len(group),
                        context={"symbol": symbol, "values": sorted(map(str, group[field].unique()))},
                    )
                )

    missing_counts: Counter[str] = Counter()
    if calendar is not None and not errors:
        for (symbol, session_date), group in frame.groupby(["symbol", "session_date"], sort=True):
            if not calendar.is_session(session_date):
                errors.append(
                    ValidationIssue(
                        code="NON_SESSION_BAR",
                        severity="error",
                        message=f"Bars assigned to non-session date {session_date}",
                        row_count=len(group),
                        context={"symbol": symbol, "session_date": str(session_date)},
                    )
                )
                continue
            session = calendar.session(session_date)
            outside = (group["bar_start_utc"] < session.open_utc) | (
                group["bar_end_utc"] > session.close_utc
            )
            if outside.any():
                errors.append(
                    ValidationIssue(
                        code="OUTSIDE_SESSION",
                        severity="error",
                        message="Regular-session bar lies outside calendar boundaries",
                        row_count=int(outside.sum()),
                        context={"symbol": symbol, "session_date": str(session_date)},
                    )
                )
            interval = int(group["interval_seconds"].iloc[0])
            expected = set(calendar.expected_bar_starts(session_date, interval))
            actual = set(timestamp.to_pydatetime() for timestamp in group["bar_start_utc"])
            completeness = 100.0 * len(expected & actual) / len(expected) if expected else 0.0
            if completeness < minimum_session_completeness_pct:
                key = f"{symbol}:{session_date}"
                missing_counts[key] = len(expected - actual)
                issue = ValidationIssue(
                    code="LOW_SESSION_COMPLETENESS",
                    severity="error" if missing_session_policy == "fail_dataset" else "warning",
                    message=(
                        f"{key} completeness {completeness:.2f}% is below "
                        f"{minimum_session_completeness_pct:.2f}%"
                    ),
                    row_count=len(expected - actual),
                    context={"completeness_pct": completeness},
                )
                if missing_session_policy == "fail_dataset":
                    errors.append(issue)
                else:
                    warnings.append(issue)
                    if missing_session_policy == "fail_session":
                        excluded.append(key)

    status = (
        ValidationStatus.FAIL
        if errors
        else ValidationStatus.PASS_WITH_WARNINGS
        if warnings
        else ValidationStatus.PASS
    )
    excluded_rows = 0
    for key in excluded:
        symbol, session = key.split(":", 1)
        excluded_rows += int(
            ((frame["symbol"] == symbol) & (frame["session_date"].astype(str) == session)).sum()
        )
    return DataValidationReport(
        status=status,
        row_count=row_count,
        valid_row_count=max(0, row_count - excluded_rows) if not errors else 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
        excluded_sessions=tuple(sorted(excluded)),
        summary={
            "symbols": sorted(frame["symbol"].unique().tolist()),
            "providers": sorted(frame["source_provider"].unique().tolist()),
            "feeds": sorted(frame["source_feed"].unique().tolist()),
            "missing_bar_counts": dict(sorted(missing_counts.items())),
        },
    )
