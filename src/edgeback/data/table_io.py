"""Parquet I/O with an explicit deterministic development fallback.

Production installs include pyarrow and therefore write genuine Parquet. The fallback exists so
core offline tests can still execute in constrained environments where binary wheels are absent.
Fallback files carry a magic header and are never represented as genuine Parquet in manifests.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

_MAGIC = b"EDGEBACK_JSON_TABLE_FALLBACK_V1\n"


def parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def write_table(frame: pd.DataFrame, path: Path, *, schema: object | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if parquet_available():
        if schema is None:
            frame.to_parquet(path, engine="pyarrow", index=False)
        else:
            import pyarrow as pa
            import pyarrow.parquet as pq

            table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True)
            pq.write_table(table, path)
        return "parquet"
    payload = frame.to_json(orient="table", date_format="iso", index=False).encode("utf-8")
    path.write_bytes(_MAGIC + payload)
    return "json_table_fallback"


def read_table(path: Path) -> pd.DataFrame:
    with path.open("rb") as handle:
        prefix = handle.read(len(_MAGIC))
        if prefix == _MAGIC:
            payload = handle.read().decode("utf-8")
            return pd.read_json(io.StringIO(payload), orient="table")
    return pd.read_parquet(path, engine="pyarrow")


def storage_format(path: Path) -> str:
    with path.open("rb") as handle:
        return "json_table_fallback" if handle.read(len(_MAGIC)) == _MAGIC else "parquet"
