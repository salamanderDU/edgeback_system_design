from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from pydantic import Field

from edgeback.config.models import BaseStrictModel
from edgeback.data.providers.interfaces import BarRequest, MarketDataProvider, RawBarBatch


class LocalImportConfig(BaseStrictModel):
    file_path: str
    symbol: str
    interval_seconds: int
    timezone: str = "America/New_York"
    timestamp_semantics: Literal["bar_start", "bar_end"] = "bar_start"
    adjustment_mode: Literal["raw", "split_adjusted", "provider_adjusted"] = "raw"
    source_feed: str = "local_file"
    session_type: Literal["regular", "pre", "post", "overnight"] = "regular"
    column_mapping: dict[str, str] = Field(default_factory=dict)


class LocalFileProvider(MarketDataProvider):
    def __init__(self, config: LocalImportConfig) -> None:
        self.config = config

    @property
    def provider_id(self) -> str:
        return "local_file"

    def fetch_bars(self, request: BarRequest) -> RawBarBatch:
        try:
            tz = ZoneInfo(self.config.timezone)
        except (ZoneInfoNotFoundError, Exception) as err:
            raise ValueError(f"Unknown timezone: {self.config.timezone}") from err

        path = Path(self.config.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {self.config.file_path}")

        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        elif path.suffix.lower() in [".parquet", ".pq"]:
            df = pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        # Column mapping
        if self.config.column_mapping:
            df = df.rename(columns=self.config.column_mapping)

        # Look for timestamp column
        if "timestamp" in df.columns:
            ts_col = "timestamp"
        elif "time" in df.columns:
            ts_col = "time"
        elif "date" in df.columns:
            ts_col = "date"
        else:
            ts_col = ""
        if not ts_col:
            raise ValueError(f"Timestamp column not found in {list(df.columns)}")

        # Parse timestamp
        ts_series = pd.to_datetime(df[ts_col])
        if ts_series.dt.tz is None:
            ts_series = ts_series.dt.tz_localize(tz)
        else:
            ts_series = ts_series.dt.tz_convert(tz)

        ts_utc = ts_series.dt.tz_convert(UTC)

        interval_delta = pd.Timedelta(seconds=self.config.interval_seconds)

        if self.config.timestamp_semantics == "bar_start":
            start_utc = ts_utc
            end_utc = ts_utc + interval_delta
        else:
            end_utc = ts_utc
            start_utc = ts_utc - interval_delta

        result_df = pd.DataFrame(
            {
                "symbol": self.config.symbol,
                "provider_symbol": self.config.symbol,
                "interval_seconds": self.config.interval_seconds,
                "bar_start_utc": pd.to_datetime(start_utc),
                "bar_end_utc": pd.to_datetime(end_utc),
                "session_date": ts_series.dt.date,
                "session_type": self.config.session_type,
                "open": df["open"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "close": df["close"].astype(float),
                "volume": df["volume"].astype(int),
                "vwap": df["vwap"].astype(float) if "vwap" in df.columns else None,
                "trade_count": df["trade_count"].astype(int)
                if "trade_count" in df.columns
                else None,
                "is_complete": True,
                "source_provider": self.provider_id,
                "source_feed": self.config.source_feed,
                "adjustment_mode": self.config.adjustment_mode,
                "ingested_at_utc": pd.Timestamp.now(UTC),
            }
        )

        # Filter by request range
        mask = (result_df["bar_start_utc"] >= pd.Timestamp(request.start_utc)) & (
            result_df["bar_end_utc"] <= pd.Timestamp(request.end_utc)
        )
        filtered_df = result_df[mask].reset_index(drop=True)

        return RawBarBatch(
            data=filtered_df,
            provider_id=self.provider_id,
            source_feed=self.config.source_feed,
            fetched_at_utc=datetime.now(UTC),
        )
