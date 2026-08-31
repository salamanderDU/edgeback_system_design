from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from edgeback.data.providers.interfaces import ProviderCapabilities
from edgeback.data.validation import DataValidationReport
from edgeback.domain.common import UTCModel


class PartitionRecord(UTCModel):
    relative_path: Path
    symbol: str
    year: int
    month: int
    row_count: int = Field(ge=0)
    checksum_sha256: str
    storage_format: str


class DatasetManifest(UTCModel):
    schema_version: str = "1.0"
    dataset_id: str
    created_at_utc: datetime
    provider: str
    feed: str
    capability_snapshot: ProviderCapabilities
    canonical_to_provider_symbols: dict[str, str]
    interval_seconds: int = Field(gt=0)
    requested_start_utc: datetime | None = None
    requested_end_utc: datetime | None = None
    actual_start_utc: datetime
    actual_end_utc: datetime
    session_types: tuple[str, ...]
    calendar_id: str
    adjustment_mode: str
    row_counts: dict[str, int]
    validation: DataValidationReport
    partitions: tuple[PartitionRecord, ...]
    aggregate_hash: str
    raw_request_ids: tuple[str, ...] = ()
    ingestion_version: str
    licensing_warning: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "created_at_utc",
        "requested_start_utc",
        "requested_end_utc",
        "actual_start_utc",
        "actual_end_utc",
    )
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return cls.ensure_aware_utc(value) if value is not None else None
