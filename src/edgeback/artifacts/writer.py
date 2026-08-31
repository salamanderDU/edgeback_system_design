"""Atomic immutable run artifact writer."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from edgeback.artifacts.registry import RunRecord, RunRegistry
from edgeback.artifacts.reproducibility import build_run_metadata, logical_run_identity
from edgeback.artifacts.tables import arrow_schema_for_table, canonical_result_tables, validate_table_linkage
from edgeback.config.models import ResolvedConfig
from edgeback.data.manifest import DatasetManifest
from edgeback.data.table_io import write_table
from edgeback.engine.state import BacktestResult
from edgeback.errors import ArtifactError
from edgeback.metrics import compute_metrics, daily_returns_table
from edgeback.reporting import render_html_report
from edgeback.utils import file_sha256, stable_hash

_REQUIRED_TABLES = ("intents", "orders", "fills", "trades", "equity", "warnings")


class RunArtifactWriter:
    def __init__(self, output_root: str | Path, *, registry: RunRegistry | None = None) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or RunRegistry(self.output_root / "registry.sqlite3")

    def write(
        self,
        *,
        config: ResolvedConfig,
        data_manifest: DatasetManifest | dict[str, Any],
        result: BacktestResult,
        conclusion_label: str,
        gate_results: dict[str, Any] | None = None,
        input_config_path: str | Path | None = None,
        parent_run_id: str | None = None,
        fold_id: str | None = None,
        started_at_utc: datetime | None = None,
    ) -> RunRecord:
        started = (started_at_utc or datetime.now(UTC)).astimezone(UTC)
        manifest_dict = (
            data_manifest.model_dump(mode="json")
            if isinstance(data_manifest, DatasetManifest)
            else json.loads(json.dumps(data_manifest, default=str))
        )
        data_hash = str(manifest_dict.get("aggregate_hash") or stable_hash(manifest_dict))
        identity = logical_run_identity(config, data_hash)
        timestamp = started.strftime("%Y%m%dT%H%M%S.%fZ")
        run_id = f"{timestamp}__{config.strategy.name}__{config.data.interval}__{identity['logical_identity_hash'][:8]}"
        final_dir = self.output_root / run_id
        if final_dir.exists():
            raise ArtifactError(f"Refusing to overwrite existing run directory: {final_dir}")
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}-", dir=self.output_root))
        try:
            self._write_json(temp_dir / "RUN_STATE.json", {"state": "CREATED", "run_id": run_id})
            self._write_json(temp_dir / "RUN_STATE.json", {"state": "RUNNING", "run_id": run_id})
            if input_config_path is not None:
                source = Path(input_config_path)
                if source.exists():
                    shutil.copyfile(source, temp_dir / "config.input.yaml")
            if not (temp_dir / "config.input.yaml").exists():
                self._write_yaml(
                    temp_dir / "config.input.yaml",
                    config.model_dump(mode="json", exclude={"resolution"}),
                )
            self._write_yaml(temp_dir / "config.resolved.yaml", config.model_dump(mode="json"))
            self._write_json(temp_dir / "data_manifest.json", manifest_dict)

            tables = canonical_result_tables(result)
            linkage_errors = validate_table_linkage(tables)
            if linkage_errors:
                raise ArtifactError("Result-table linkage failed: " + "; ".join(linkage_errors))
            for name, frame in tables.items():
                write_table(frame, temp_dir / f"{name}.parquet", schema=arrow_schema_for_table(name))
                if config.report.write_csv_copies:
                    frame.to_csv(temp_dir / f"{name}.csv", index=False)
            missing = [name for name in _REQUIRED_TABLES if not (temp_dir / f"{name}.parquet").exists()]
            if missing:
                raise ArtifactError(f"Required artifact tables were not written: {missing}")

            validation = manifest_dict.get("validation", {})
            metrics = compute_metrics(
                tables,
                starting_equity_usd=config.engine.initial_cash_usd,
                data_completeness_pct=validation.get("overall_completeness_pct"),
                excluded_sessions=len(validation.get("excluded_sessions", [])),
            )
            daily = daily_returns_table(tables["equity"], config.engine.initial_cash_usd)
            write_table(daily, temp_dir / "daily_returns.parquet")
            if config.report.write_csv_copies:
                daily.to_csv(temp_dir / "daily_returns.csv", index=False)
            self._write_json(temp_dir / "metrics.json", metrics)
            self._write_json(temp_dir / "gate_results.json", gate_results or {"label": conclusion_label, "gates": []})
            self._write_json(
                temp_dir / "warnings.json",
                [item.model_dump(mode="json") for item in result.warnings],
            )
            log_records = [
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "level": "INFO" if result.status.value == "COMPLETED" else "ERROR",
                    "component": "engine",
                    "run_id": run_id,
                    "event": "RUN_FINISHED",
                    "status": result.status.value,
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                }
            ]
            (temp_dir / "logs.jsonl").write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in log_records),
                encoding="utf-8",
            )
            if result.traceback_text:
                (temp_dir / "failure_traceback.txt").write_text(result.traceback_text, encoding="utf-8")

            finished = datetime.now(UTC)
            preliminary = build_run_metadata(
                run_id=run_id,
                status=result.status.value,
                config=config,
                data_hash=data_hash,
                started_at_utc=started,
                finished_at_utc=finished,
                conclusion_label=conclusion_label,
                parent_run_id=parent_run_id,
                fold_id=fold_id,
            )
            report = render_html_report(
                metadata=preliminary,
                config=config,
                data_manifest=manifest_dict,
                metrics=metrics,
                tables=tables,
                gate_results=gate_results,
            )
            if config.report.html:
                (temp_dir / "report.html").write_text(report, encoding="utf-8")
            checksums = {
                path.name: file_sha256(path)
                for path in sorted(temp_dir.iterdir())
                if path.is_file() and path.name not in {"RUN_STATE.json", "run_metadata.json"}
            }
            metadata = build_run_metadata(
                run_id=run_id,
                status=result.status.value,
                config=config,
                data_hash=data_hash,
                started_at_utc=started,
                finished_at_utc=finished,
                conclusion_label=conclusion_label,
                artifact_checksums=checksums,
                parent_run_id=parent_run_id,
                fold_id=fold_id,
            )
            self._write_json(temp_dir / "run_metadata.json", metadata)
            for artifact_name, expected_checksum in checksums.items():
                if file_sha256(temp_dir / artifact_name) != expected_checksum:
                    raise ArtifactError(f"Artifact checksum verification failed before commit: {artifact_name}")
            final_state = "COMPLETED" if result.status.value == "COMPLETED" else "FAILED"
            self._write_json(
                temp_dir / "RUN_STATE.json",
                {"state": final_state, "run_id": run_id, "finished_at_utc": finished.isoformat()},
            )
            os.replace(temp_dir, final_dir)
            return self.registry.register(metadata, final_dir)
        except Exception as exc:
            if temp_dir.exists():
                failed_dir = self.output_root / f"{run_id}__artifact_failed"
                try:
                    self._write_json(
                        temp_dir / "RUN_STATE.json",
                        {"state": "FAILED", "run_id": run_id, "artifact_error": str(exc)},
                    )
                    if not failed_dir.exists():
                        os.replace(temp_dir, failed_dir)
                except OSError:
                    pass
            if isinstance(exc, ArtifactError):
                raise
            raise ArtifactError(f"Could not write run artifacts: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")

    @staticmethod
    def _write_yaml(path: Path, value: Any) -> None:
        path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")
