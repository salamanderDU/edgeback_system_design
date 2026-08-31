"""Reproducibility identity and non-sensitive code/runtime metadata."""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edgeback import __version__
from edgeback.artifacts.schemas import RunMetadata
from edgeback.config import config_hash
from edgeback.config.models import ResolvedConfig
from edgeback.utils import package_versions, stable_hash


def git_metadata(root: Path | None = None) -> dict[str, Any]:
    cwd = root or Path.cwd()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, check=True, capture_output=True, text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, check=True, capture_output=True, text=True,
            timeout=5,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def runtime_metadata() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "edgeback_version": __version__,
        "packages": package_versions(
            ("pydantic", "pandas", "pyarrow", "PyYAML", "typer", "exchange-calendars")
        ),
    }


def logical_run_identity(config: ResolvedConfig, data_hash: str) -> dict[str, Any]:
    identity = {
        "config_hash": config_hash(config),
        "data_manifest_hash": data_hash,
        "strategy_id": config.strategy.name,
        "strategy_version": config.strategy.expected_version,
        "strategy_params_hash": stable_hash(config.strategy.params),
        "engine_version": __version__,
        "seed": config.project.random_seed,
        "execution_model": {
            "fill_timing": config.engine.market_fill_timing,
            "same_bar_policy": config.engine.same_bar_bracket_policy,
            "spread": config.execution.spread.model_dump(mode="json"),
            "slippage": config.execution.slippage.model_dump(mode="json"),
            "commission": config.execution.commission.model_dump(mode="json"),
        },
    }
    identity["logical_identity_hash"] = stable_hash(identity)
    return identity


def build_run_metadata(
    *,
    run_id: str,
    status: str,
    config: ResolvedConfig,
    data_hash: str,
    started_at_utc: datetime,
    finished_at_utc: datetime,
    conclusion_label: str,
    artifact_checksums: dict[str, str] | None = None,
    parent_run_id: str | None = None,
    fold_id: str | None = None,
) -> dict[str, Any]:
    identity = logical_run_identity(config, data_hash)
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "research_id": None,
        "trial_id": None,
        "parent_run_id": parent_run_id,
        "fold_id": fold_id,
        "status": status,
        "started_at_utc": started_at_utc.astimezone(UTC).isoformat(),
        "finished_at_utc": finished_at_utc.astimezone(UTC).isoformat(),
        "duration_seconds": max(0.0, (finished_at_utc - started_at_utc).total_seconds()),
        "strategy": {
            "id": config.strategy.name,
            "version": config.strategy.expected_version,
            "parameters": config.strategy.params,
        },
        **identity,
        "code": git_metadata(),
        "runtime": runtime_metadata(),
        "artifact_checksums": artifact_checksums or {},
        "conclusion_label": conclusion_label,
    }
    return RunMetadata.model_validate(payload).model_dump(mode="json")
