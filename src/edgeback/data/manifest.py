from datetime import datetime

from pydantic import Field

from edgeback.config.models import BaseStrictModel
from edgeback.data.schema import DataValidationReport


class ProviderCapabilitySnapshot(BaseStrictModel):
    provider_id: str
    interval_seconds: list[int]
    supports_pre_market: bool = False
    supports_post_market: bool = False


class PartitionInfo(BaseStrictModel):
    path: str
    symbol: str
    row_count: int
    checksum: str
    size_bytes: int = 0


class DatasetStats(BaseStrictModel):
    row_count: int
    missing_bars: int = 0
    duplicate_bars: int = 0
    invalid_bars: int = 0


class DatasetManifest(BaseStrictModel):
    dataset_id: str
    schema_version: str = "1.0"
    provider: str
    source_feed: str
    provider_capabilities: ProviderCapabilitySnapshot
    symbols: list[str]
    provider_symbols: list[str]
    interval_seconds: int
    requested_start_utc: datetime
    requested_end_utc: datetime
    session_types_included: list[str] = Field(default_factory=lambda: ["regular"])
    exchange_calendar_id: str = "XNYS"
    adjustment_mode: str = "split_adjusted"
    stats: DatasetStats
    validation_report: DataValidationReport = Field(default_factory=DataValidationReport)
    partitions: list[PartitionInfo] = Field(default_factory=list)
    aggregate_hash: str = ""
    ingested_at_utc: datetime
