"""SQLite index for immutable run directories.

The registry is an index only.  Every critical field is mirrored in each run directory so deleting
this database never makes completed experiments unreadable.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from edgeback.errors import ArtifactError


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    status: str
    strategy_id: str
    strategy_version: str | None = None
    logical_identity_hash: str
    path: Path
    created_at_utc: datetime
    conclusion_label: str
    parent_run_id: str | None = None
    fold_id: str | None = None


class RunRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT,
                    logical_identity_hash TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    conclusion_label TEXT NOT NULL,
                    parent_run_id TEXT,
                    fold_id TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_identity ON runs(logical_identity_hash)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at_utc DESC)"
            )

    def register(self, metadata: dict[str, Any], path: str | Path) -> RunRecord:
        record = RunRecord(
            run_id=str(metadata["run_id"]),
            status=str(metadata["status"]),
            strategy_id=str(metadata["strategy"]["id"]),
            strategy_version=metadata["strategy"].get("version"),
            logical_identity_hash=str(metadata["logical_identity_hash"]),
            path=Path(path).resolve(),
            created_at_utc=datetime.fromisoformat(str(metadata["started_at_utc"])).astimezone(UTC),
            conclusion_label=str(metadata["conclusion_label"]),
            parent_run_id=metadata.get("parent_run_id"),
            fold_id=metadata.get("fold_id"),
        )
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """
                    INSERT INTO runs(
                        run_id,status,strategy_id,strategy_version,logical_identity_hash,path,
                        created_at_utc,conclusion_label,parent_run_id,fold_id,metadata_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.run_id,
                        record.status,
                        record.strategy_id,
                        record.strategy_version,
                        record.logical_identity_hash,
                        str(record.path),
                        record.created_at_utc.isoformat(),
                        record.conclusion_label,
                        record.parent_run_id,
                        record.fold_id,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ArtifactError(f"Run registry refuses duplicate run/path: {record.run_id}") from exc
        return record

    def get(self, run_id: str) -> RunRecord:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise ArtifactError(f"Run not found in registry: {run_id}")
        return self._row_to_record(row)

    def list(self, *, limit: int = 100) -> tuple[RunRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at_utc DESC, run_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    def find_logical_duplicates(self, logical_identity_hash: str) -> tuple[RunRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE logical_identity_hash = ? ORDER BY created_at_utc",
                (logical_identity_hash,),
            ).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            status=row["status"],
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            logical_identity_hash=row["logical_identity_hash"],
            path=Path(row["path"]),
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]).astimezone(UTC),
            conclusion_label=row["conclusion_label"],
            parent_run_id=row["parent_run_id"],
            fold_id=row["fold_id"],
        )
