from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from edgeback.data.normalization import normalize_provider_frame
from edgeback.data.providers.interfaces import (
    BarRequest,
    ProviderCapabilities,
    ProviderSymbol,
    RawBarBatch,
)
from edgeback.data.table_io import read_table
from edgeback.domain import Bar
from edgeback.errors import DataUnavailableError


class LocalFileProvider:
    provider_id = "local"

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            feeds=("user_supplied",),
            intervals=("1m", "5m", "15m"),
            limitations=(
                "Quality, licensing, timestamp semantics and adjustments are user-supplied.",
                "Use data import with explicit column mapping and timezone semantics.",
            ),
        )

    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol:
        normalized = canonical_symbol.strip().upper()
        return ProviderSymbol(canonical_symbol=normalized, provider_symbol=normalized)

    def fetch_bars(self, request: BarRequest) -> RawBarBatch:
        del request
        raise DataUnavailableError(
            "The local provider does not fetch data; use `edgeback data import` with a file path"
        )

    def import_file(
        self,
        path: str | Path,
        *,
        symbol: str,
        interval_seconds: int,
        timestamp_column: str,
        timestamp_semantics: str,
        source_timezone: str,
        feed: str,
        adjustment_mode: str,
        column_map: Mapping[str, str] | None = None,
    ) -> tuple[Bar, ...]:
        source = Path(path)
        if not source.exists():
            raise DataUnavailableError(f"Local data file not found: {source}")
        if source.suffix.lower() == ".csv":
            frame = pd.read_csv(source)
        elif source.suffix.lower() in {".parquet", ".pq"}:
            frame = read_table(source)
        else:
            raise DataUnavailableError("Local provider supports only CSV and Parquet")
        if column_map:
            # Mapping is source-name -> canonical-name and is explicit, never inferred.
            frame = frame.rename(columns=dict(column_map))
        return normalize_provider_frame(
            frame,
            symbol=symbol,
            provider_symbol=symbol,
            provider=self.provider_id,
            feed=feed,
            interval_seconds=interval_seconds,
            timestamp_column=timestamp_column,
            timestamp_semantics=timestamp_semantics,
            source_timezone=source_timezone,
            adjustment_mode=adjustment_mode,
        )
