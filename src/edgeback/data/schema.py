from __future__ import annotations

from typing import Final

import pandas as pd

from edgeback.domain import Bar

CANONICAL_BAR_COLUMNS: Final[tuple[str, ...]] = (
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
    "vwap",
    "trade_count",
    "is_complete",
    "source_provider",
    "source_feed",
    "adjustment_mode",
    "ingested_at_utc",
)


def bars_to_frame(bars: list[Bar] | tuple[Bar, ...]) -> pd.DataFrame:
    records = [bar.model_dump(mode="python") for bar in bars]
    frame = pd.DataFrame.from_records(records, columns=CANONICAL_BAR_COLUMNS)
    if frame.empty:
        return frame
    for name in ("bar_start_utc", "bar_end_utc", "ingested_at_utc"):
        frame[name] = pd.to_datetime(frame[name], utc=True)
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    frame["session_type"] = frame["session_type"].map(
        lambda value: value.value if hasattr(value, "value") else str(value)
    )
    frame = frame.sort_values(["bar_end_utc", "symbol"], kind="stable").reset_index(drop=True)
    return frame


def frame_to_bars(frame: pd.DataFrame) -> tuple[Bar, ...]:
    missing = set(CANONICAL_BAR_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"canonical frame missing columns: {sorted(missing)}")
    working = frame.loc[:, CANONICAL_BAR_COLUMNS].copy()
    for column in ("vwap", "trade_count"):
        working[column] = working[column].where(working[column].notna(), None)
    records = working.to_dict(orient="records")
    for record in records:
        if pd.isna(record.get("vwap")):
            record["vwap"] = None
        if pd.isna(record.get("trade_count")):
            record["trade_count"] = None
    return tuple(Bar.model_validate(record) for record in records)


def arrow_schema() -> object | None:
    try:
        import pyarrow as pa
    except ImportError:
        return None
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("provider_symbol", pa.string(), nullable=False),
            pa.field("interval_seconds", pa.int32(), nullable=False),
            pa.field("bar_start_utc", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("bar_end_utc", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("session_date", pa.date32(), nullable=False),
            pa.field("session_type", pa.string(), nullable=False),
            pa.field("open", pa.float64(), nullable=False),
            pa.field("high", pa.float64(), nullable=False),
            pa.field("low", pa.float64(), nullable=False),
            pa.field("close", pa.float64(), nullable=False),
            pa.field("volume", pa.int64(), nullable=False),
            pa.field("vwap", pa.float64(), nullable=True),
            pa.field("trade_count", pa.int64(), nullable=True),
            pa.field("is_complete", pa.bool_(), nullable=False),
            pa.field("source_provider", pa.string(), nullable=False),
            pa.field("source_feed", pa.string(), nullable=False),
            pa.field("adjustment_mode", pa.string(), nullable=False),
            pa.field("ingested_at_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        ]
    )
