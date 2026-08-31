"""Independent verification of a completed or failed run directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edgeback.artifacts.schemas import RunMetadata
from edgeback.errors import ArtifactError
from edgeback.utils import file_sha256

_REQUIRED_FILES = {
    "RUN_STATE.json",
    "config.input.yaml",
    "config.resolved.yaml",
    "run_metadata.json",
    "data_manifest.json",
    "warnings.json",
    "logs.jsonl",
    "intents.parquet",
    "orders.parquet",
    "fills.parquet",
    "trades.parquet",
    "equity.parquet",
    "daily_returns.parquet",
    "metrics.json",
    "gate_results.json",
}


def verify_run_directory(path: str | Path) -> dict[str, Any]:
    run_dir = Path(path)
    if not run_dir.is_dir():
        raise ArtifactError(f"Run directory does not exist: {run_dir}")
    missing = sorted(name for name in _REQUIRED_FILES if not (run_dir / name).is_file())
    if missing:
        raise ArtifactError(f"Run directory is missing required files: {missing}")
    state = json.loads((run_dir / "RUN_STATE.json").read_text(encoding="utf-8"))
    if state.get("state") not in {"COMPLETED", "FAILED"}:
        raise ArtifactError(f"Run state is not final: {state.get('state')}")
    metadata = RunMetadata.model_validate_json(
        (run_dir / "run_metadata.json").read_text(encoding="utf-8")
    )
    mismatches: list[str] = []
    for name, expected in metadata.artifact_checksums.items():
        artifact = run_dir / name
        if not artifact.is_file():
            mismatches.append(f"missing:{name}")
        elif file_sha256(artifact) != expected:
            mismatches.append(f"checksum:{name}")
    if mismatches:
        raise ArtifactError("Run artifact verification failed: " + ", ".join(mismatches))
    return {
        "run_id": metadata.run_id,
        "status": metadata.status,
        "state": state["state"],
        "verified_artifact_count": len(metadata.artifact_checksums),
        "verified": True,
    }
