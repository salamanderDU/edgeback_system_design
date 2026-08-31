from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from edgeback.domain import Bar, SessionType
from edgeback.errors import DataValidationError


_REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")


def normalize_provider_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    provider_symbol: str,
    provider: str,
    feed: str,
    interval_seconds: int,
    timestamp_column: str | None = None,
    timestamp_semantics: str = "bar_start",
    source_timezone: str | None = None,
    adjustment_mode: str = "split_adjusted",
    session_type: str = "regular",
    ingested_at_utc: datetime | None = None,
) -> tuple[Bar, ...]:
    if timestamp_semantics not in {"bar_start", "bar_end"}:
        raise DataValidationError("timestamp_semantics must be bar_start or bar_end")
    if interval_seconds <= 0:
        raise DataValidationError("interval_seconds must be positive")
    working = frame.copy(deep=True)
    working.columns = [str(column).strip().lower().replace(" ", "_") for column in working.columns]
    missing = sorted(set(_REQUIRED_OHLCV) - set(working.columns))
    if missing:
        raise DataValidationError(f"Provider frame missing OHLCV columns: {missing}")

    if timestamp_column is None:
        if isinstance(working.index, pd.DatetimeIndex):
            timestamps = pd.Series(working.index, index=working.index)
        else:
            for candidate in ("timestamp", "datetime", "date", "time"):
                if candidate in working.columns:
                    timestamp_column = candidate
                    break
            if timestamp_column is None:
                raise DataValidationError("Timestamp column is ambiguous or missing")
            timestamps = working[timestamp_column]
    else:
        normalized_name = timestamp_column.strip().lower().replace(" ", "_")
        if normalized_name not in working.columns:
            raise DataValidationError(f"Timestamp column {timestamp_column!r} not found")
        timestamps = working[normalized_name]

    parsed = pd.to_datetime(timestamps, errors="raise")
    if getattr(parsed.dt, "tz", None) is None:
        if not source_timezone:
            raise DataValidationError("Timezone-naive input requires explicit source_timezone")
        try:
            parsed = parsed.dt.tz_localize(ZoneInfo(source_timezone), ambiguous="raise", nonexistent="raise")
        except Exception as exc:
            raise DataValidationError(f"Could not localize source timestamps: {exc}") from exc
    parsed = parsed.dt.tz_convert("UTC")
    step = pd.to_timedelta(interval_seconds, unit="s")
    if timestamp_semantics == "bar_start":
        starts = parsed
        ends = parsed + step
    else:
        ends = parsed
        starts = parsed - step

    local_zone = ZoneInfo("America/New_York")
    ingested = (ingested_at_utc or datetime.now(UTC)).astimezone(UTC)
    bars: list[Bar] = []
    for position, (_, row) in enumerate(working.reset_index(drop=True).iterrows()):
        start = starts.iloc[position].to_pydatetime().astimezone(UTC)
        end = ends.iloc[position].to_pydatetime().astimezone(UTC)
        local_date: date = start.astimezone(local_zone).date()
        bars.append(
            Bar(
                symbol=symbol,
                provider_symbol=provider_symbol,
                interval_seconds=interval_seconds,
                bar_start_utc=start,
                bar_end_utc=end,
                session_date=local_date,
                session_type=SessionType(session_type),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                vwap=float(row["vwap"]) if "vwap" in row and pd.notna(row["vwap"]) else None,
                trade_count=(
                    int(row["trade_count"])
                    if "trade_count" in row and pd.notna(row["trade_count"])
                    else None
                ),
                is_complete=(
                    bool(row["is_complete"]) if "is_complete" in row else end <= ingested
                ),
                source_provider=provider,
                source_feed=feed,
                adjustment_mode=adjustment_mode,
                ingested_at_utc=ingested,
            )
        )
    return tuple(sorted(bars, key=lambda bar: (bar.bar_end_utc, bar.symbol)))
