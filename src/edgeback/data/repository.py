import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from edgeback.data.manifest import DatasetManifest, PartitionInfo


class ParquetRepository:
    def __init__(self, data_dir: Path | str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.canonical_dir = self.data_dir / "canonical" / "bars"
        self.manifests_dir = self.data_dir / "manifests"

        self.canonical_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def write_partition(
        self,
        df: pd.DataFrame,
        provider: str,
        feed: str,
        interval: int,
        symbol: str,
        year: int,
        month: int,
    ) -> PartitionInfo:
        if df.empty:
            raise ValueError("Cannot write empty dataframe")

        rel_dir = (
            Path("canonical")
            / "bars"
            / f"provider={provider}"
            / f"feed={feed}"
            / f"interval={interval}"
            / f"symbol={symbol}"
            / f"year={year}"
            / f"month={month:02d}"
        )
        full_dir = self.data_dir / rel_dir
        full_dir.mkdir(parents=True, exist_ok=True)

        file_path = full_dir / "bars.parquet"
        rel_path = str(rel_dir / "bars.parquet").replace("\\", "/")

        table = pa.Table.from_pandas(df)
        pq.write_table(table, file_path)

        with open(file_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()

        size_bytes = file_path.stat().st_size

        return PartitionInfo(
            path=rel_path,
            symbol=symbol,
            row_count=len(df),
            checksum=checksum,
            size_bytes=size_bytes,
        )

    def write_manifest(self, manifest: DatasetManifest) -> None:
        manifest_path = self.manifests_dir / f"{manifest.dataset_id}.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

    def get_manifest(self, dataset_id: str) -> DatasetManifest | None:
        manifest_path = self.manifests_dir / f"{dataset_id}.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        return DatasetManifest.model_validate(data)

    def read_dataset(self, dataset_id: str) -> pd.DataFrame | None:
        manifest = self.get_manifest(dataset_id)
        if manifest is None:
            return None

        dfs = []
        for part in manifest.partitions:
            part_path = self.data_dir / part.path
            if part_path.exists():
                df = pd.read_parquet(part_path)
                dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)
