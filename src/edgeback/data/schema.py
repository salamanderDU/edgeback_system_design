from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from edgeback.config.models import BaseStrictModel


class DataValidationIssue(BaseStrictModel):
    code: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING
    details: dict[str, Any] = Field(default_factory=dict)


class DataValidationReport(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    is_valid: bool = True
    issues: list[DataValidationIssue] = Field(default_factory=list)

    def add_issue(
        self,
        code: str,
        message: str,
        severity: str = "ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(
            DataValidationIssue(
                code=code,
                message=message,
                severity=severity,
                details=details or {},
            )
        )
        if severity == "ERROR":
            self.is_valid = False


REQUIRED_COLUMNS = [
    "symbol",
    "provider_symbol",
    "interval_seconds",
    "bar_start_utc",
    "bar_end_utc",
    "session_date",
    "session_type",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "is_complete",
    "source_provider",
    "source_feed",
    "adjustment_mode",
    "ingested_at_utc",
]


def validate_dataframe(df: pd.DataFrame) -> DataValidationReport:
    report = DataValidationReport()

    # 1. Missing columns check
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        report.add_issue(
            code="MISSING_COLUMNS",
            message=f"Missing required columns: {missing}",
            details={"missing_columns": missing},
        )
        return report

    if len(df) == 0:
        return report

    # 2. Timezone checks
    for col in ["bar_start_utc", "bar_end_utc", "ingested_at_utc"]:
        series = df[col]
        if not pd.api.types.is_datetime64_any_dtype(series):
            try:
                converted = pd.to_datetime(series)
                if converted.dt.tz is None:
                    report.add_issue(
                        code="INVALID_DATETIME_TYPE",
                        message=f"Column {col} must be timezone-aware (UTC)",
                    )
            except Exception:
                report.add_issue(
                    code="INVALID_DATETIME_TYPE",
                    message=f"Column {col} cannot be parsed as datetime",
                )
        else:
            if series.dt.tz is None:
                report.add_issue(
                    code="INVALID_DATETIME_TYPE",
                    message=f"Column {col} must be timezone-aware (UTC)",
                )

    # 3. OHLC bounds
    invalid_open = df[(df["open"] < df["low"]) | (df["open"] > df["high"])]
    if len(invalid_open) > 0:
        report.add_issue(
            code="INVALID_OPEN",
            message="Open price is outside [low, high] interval",
            details={"count": len(invalid_open)},
        )

    invalid_close = df[(df["close"] < df["low"]) | (df["close"] > df["high"])]
    if len(invalid_close) > 0:
        report.add_issue(
            code="INVALID_CLOSE",
            message="Close price is outside [low, high] interval",
            details={"count": len(invalid_close)},
        )

    invalid_high_low = df[df["high"] < df["low"]]
    if len(invalid_high_low) > 0:
        report.add_issue(
            code="INVALID_HIGH_LOW",
            message="High price is strictly lower than low price",
            details={"count": len(invalid_high_low)},
        )

    # 4. Duplicate bars check
    duplicates = df[
        df.duplicated(subset=["symbol", "interval_seconds", "bar_start_utc"], keep=False)
    ]
    if len(duplicates) > 0:
        report.add_issue(
            code="DUPLICATE_BARS",
            message="Duplicate bars found for the same symbol, interval, and bar_start_utc",
            details={"duplicate_count": len(duplicates)},
        )

    return report
