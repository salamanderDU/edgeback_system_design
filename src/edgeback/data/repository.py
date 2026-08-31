from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from edgeback import __version__
from edgeback.calendar import TradingCalendar
from edgeback.data.manifest import DatasetManifest, PartitionRecord
from edgeback.data.providers.interfaces import ProviderCapabilities
from edgeback.data.schema import arrow_schema, bars_to_frame, frame_to_bars
from edgeback.data.table_io import read_table, write_table
from edgeback.data.validation import validate_bars
from edgeback.domain import Bar
from edgeback.errors import DataUnavailableError, DataValidationError
from edgeback.utils import file_sha256, stable_hash


class DataRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.canonical_root = self.root / "canonical" / "bars"
        self.manifest_root = self.root / "manifests"
        self.validation_root = self.root / "validation"
        self.canonical_root.mkdir(parents=True, exist_ok=True)
        self.manifest_root.mkdir(parents=True, exist_ok=True)
        self.validation_root.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        bars: tuple[Bar, ...] | list[Bar],
        *,
        calendar: TradingCalendar,
        capabilities: ProviderCapabilities,
        minimum_session_completeness_pct: float,
        missing_session_policy: str,
        requested_start_utc: datetime | None = None,
        requested_end_utc: datetime | None = None,
        raw_request_ids: tuple[str, ...] = (),
        licensing_warning: str = "User is responsible for provider terms and data licensing.",
    ) -> DatasetManifest:
        if not bars:
            raise DataValidationError("Cannot ingest an empty bar sequence")
        frame = bars_to_frame(tuple(bars))
        report = validate_bars(
            frame,
            calendar=calendar,
            minimum_session_completeness_pct=minimum_session_completeness_pct,
            missing_session_policy=missing_session_policy,
        )
        if not report.passed:
            raise DataValidationError(
                "Canonical data validation failed: "
                + "; ".join(issue.code for issue in report.errors)
            )
        if report.excluded_sessions:
            excluded_pairs = {tuple(item.split(":", 1)) for item in report.excluded_sessions}
            mask = [
                (str(row.symbol), str(row.session_date)) not in excluded_pairs
                for row in frame.itertuples()
            ]
            frame = frame.loc[mask].reset_index(drop=True)
        if frame.empty:
            raise DataValidationError("All sessions were excluded by validation")

        identity_payload = frame.copy(deep=True)
        # Acquisition time is provenance, not canonical market content identity.
        identity_payload["ingested_at_utc"] = "<normalized>"
        dataset_id = stable_hash(
            {
                "provider": frame["source_provider"].iloc[0],
                "feed": frame["source_feed"].iloc[0],
                "rows": identity_payload.to_dict(orient="records"),
            }
        )[:24]
        existing = self.manifest_root / f"{dataset_id}.json"
        if existing.exists():
            return self.load_manifest(dataset_id)

        temp_parent = self.root / ".tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f"dataset-{dataset_id}-", dir=temp_parent))
        partitions: list[PartitionRecord] = []
        try:
            for (symbol, year, month), group in frame.groupby(
                ["symbol", frame["bar_start_utc"].dt.year, frame["bar_start_utc"].dt.month],
                sort=True,
            ):
                relative = Path(
                    f"provider={frame['source_provider'].iloc[0]}/"
                    f"feed={frame['source_feed'].iloc[0]}/"
                    f"interval={int(frame['interval_seconds'].iloc[0])}/"
                    f"symbol={symbol}/year={int(year):04d}/month={int(month):02d}/"
                    f"{dataset_id}.parquet"
                )
                staged = temp_dir / relative
                fmt = write_table(group.reset_index(drop=True), staged, schema=arrow_schema())
                partitions.append(
                    PartitionRecord(
                        relative_path=relative,
                        symbol=str(symbol),
                        year=int(year),
                        month=int(month),
                        row_count=len(group),
                        checksum_sha256=file_sha256(staged),
                        storage_format=fmt,
                    )
                )

            provider = str(frame["source_provider"].iloc[0])
            feed = str(frame["source_feed"].iloc[0])
            adjustment = str(frame["adjustment_mode"].iloc[0])
            symbols = sorted(frame["symbol"].unique().tolist())
            provider_symbols = {
                symbol: str(frame.loc[frame["symbol"] == symbol, "provider_symbol"].iloc[0])
                for symbol in symbols
            }
            aggregate_hash = stable_hash(
                [(str(part.relative_path), part.checksum_sha256) for part in partitions]
            )
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at_utc=datetime.now(UTC),
                provider=provider,
                feed=feed,
                capability_snapshot=capabilities,
                canonical_to_provider_symbols=provider_symbols,
                interval_seconds=int(frame["interval_seconds"].iloc[0]),
                requested_start_utc=requested_start_utc,
                requested_end_utc=requested_end_utc,
                actual_start_utc=frame["bar_start_utc"].min().to_pydatetime(),
                actual_end_utc=frame["bar_end_utc"].max().to_pydatetime(),
                session_types=tuple(sorted(frame["session_type"].unique().tolist())),
                calendar_id=calendar.calendar_id,
                adjustment_mode=adjustment,
                row_counts=dict(Counter(frame["symbol"])),
                validation=report,
                partitions=tuple(partitions),
                aggregate_hash=aggregate_hash,
                raw_request_ids=raw_request_ids,
                ingestion_version=__version__,
                licensing_warning=licensing_warning,
                metadata={
                    "storage_warning": (
                        "pyarrow unavailable; deterministic JSON-table fallback used"
                        if any(part.storage_format != "parquet" for part in partitions)
                        else None
                    )
                },
            )

            for part in partitions:
                source = temp_dir / part.relative_path
                target = self.canonical_root / part.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise DataValidationError(f"Refusing to overwrite canonical partition {target}")
                source.replace(target)
            manifest_path = self.manifest_root / f"{dataset_id}.json"
            validation_path = self.validation_root / f"{dataset_id}.json"
            manifest_path.write_text(
                json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            validation_path.write_text(
                json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return manifest
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def load_manifest(self, dataset_id: str) -> DatasetManifest:
        path = self.manifest_root / f"{dataset_id}.json"
        if not path.exists():
            raise DataUnavailableError(f"Dataset manifest not found: {dataset_id}")
        return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def load_bars(self, dataset_id: str) -> tuple[Bar, ...]:
        manifest = self.load_manifest(dataset_id)
        frames: list[pd.DataFrame] = []
        for partition in manifest.partitions:
            path = self.canonical_root / partition.relative_path
            if not path.exists():
                raise DataUnavailableError(f"Dataset partition missing: {path}")
            if file_sha256(path) != partition.checksum_sha256:
                raise DataValidationError(f"Dataset partition checksum mismatch: {path}")
            frames.append(read_table(path))
        combined = pd.concat(frames, ignore_index=True)
        combined["bar_start_utc"] = pd.to_datetime(combined["bar_start_utc"], utc=True)
        combined["bar_end_utc"] = pd.to_datetime(combined["bar_end_utc"], utc=True)
        combined["ingested_at_utc"] = pd.to_datetime(combined["ingested_at_utc"], utc=True)
        combined["session_date"] = pd.to_datetime(combined["session_date"]).dt.date
        combined = combined.sort_values(["bar_end_utc", "symbol"], kind="stable").reset_index(drop=True)
        return frame_to_bars(combined)

    def list_manifests(self) -> tuple[DatasetManifest, ...]:
        manifests = [
            DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.manifest_root.glob("*.json"))
        ]
        return tuple(sorted(manifests, key=lambda item: (item.created_at_utc, item.dataset_id)))

    def find_compatible(
        self,
        *,
        provider: str,
        feed: str,
        symbols: tuple[str, ...],
        interval_seconds: int,
    ) -> DatasetManifest:
        candidates = [
            item
            for item in self.list_manifests()
            if item.provider == provider
            and item.feed == feed
            and item.interval_seconds == interval_seconds
            and set(symbols).issubset(item.canonical_to_provider_symbols)
        ]
        if not candidates:
            raise DataUnavailableError(
                "No compatible canonical dataset. Run `edgeback data download` or `data import` first."
            )
        return candidates[-1]
