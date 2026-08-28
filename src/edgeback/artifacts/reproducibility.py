import hashlib
import json
import logging
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from edgeback.config.models import BacktestConfig, BaseStrictModel

logger = logging.getLogger(__name__)


class StrategyRef(BaseStrictModel):
    id: str
    version: str
    parameters_hash: str


class ArtifactRef(BaseStrictModel):
    path: str
    sha256: str
    media_type: str | None = None


class RunMetadata(BaseStrictModel):
    schema_version: str = "1.0"
    run_id: str = Field(min_length=8)
    research_id: str | None = None
    trial_id: str | None = None
    parent_run_id: str | None = None

    status: Literal["CREATED", "RUNNING", "COMPLETED", "FAILED"]
    created_at_utc: datetime
    completed_at_utc: datetime | None = None

    strategy: StrategyRef
    config_hash: str
    data_manifest_hash: str
    git_commit: str | None = None
    git_dirty: bool | None = None
    python_version: str | None = None
    dependency_snapshot_hash: str | None = None
    random_seed: int

    execution_models: dict[str, Any] = Field(default_factory=dict)
    conclusion_label: (
        Literal[
            "ENGINE_VALIDATION_ONLY",
            "INSUFFICIENT_EVIDENCE",
            "IN_SAMPLE_ONLY",
            "OOS_FAILED",
            "OOS_PROMISING_NOT_ROBUST",
            "ROBUST_ON_TESTED_DATA",
        ]
        | None
    ) = None

    warnings: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_times(self: "RunMetadata") -> "RunMetadata":
        if self.created_at_utc.tzinfo is None:
            raise ValueError("created_at_utc must be timezone aware")
        if self.completed_at_utc is not None and self.completed_at_utc.tzinfo is None:
            raise ValueError("completed_at_utc must be timezone aware")
        return self


def compute_config_hash(config: BacktestConfig) -> str:
    """
    Computes a stable hash of the BacktestConfig.
    Excludes pure IO concepts like output_dir or report toggles so logical runs match.
    """
    d = config.model_dump(mode="json")

    # Exclude report details which shouldn't change the execution semantics
    if "report" in d:
        del d["report"]

    stable_json = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


def compute_dict_hash(data: dict[str, Any]) -> str:
    """Computes a stable hash for arbitrary dictionaries (like parameters)."""
    stable_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


def get_git_metadata(cwd: Path | None = None) -> tuple[str | None, bool | None]:
    """Safe retrieval of git state; won't fail out if git is missing."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=cwd, stderr=subprocess.DEVNULL, text=True
        ).strip()

        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=cwd, stderr=subprocess.DEVNULL, text=True
        )
        is_dirty = len(status.strip()) > 0
        return commit, is_dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None


def capture_system_metadata() -> dict[str, Any]:
    git_commit, git_dirty = get_git_metadata()
    return {
        "python_version": platform.python_version(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
    }


def initialize_run(config: BacktestConfig, strategy_version: str) -> RunMetadata:
    """Initialize a reproducible wrapper for an experiment"""
    sys_meta = capture_system_metadata()

    # Basic deterministic generator
    now = datetime.now(UTC)
    encoded_str = f"{now.isoformat()}-{config.project.random_seed}".encode()
    base_id = hashlib.sha256(encoded_str).hexdigest()[:12]

    return RunMetadata(
        run_id=f"run-{base_id}",
        status="CREATED",
        created_at_utc=now,
        strategy=StrategyRef(
            id=config.strategy.name,
            version=strategy_version,
            parameters_hash=compute_dict_hash(config.strategy.params),
        ),
        config_hash=compute_config_hash(config),
        data_manifest_hash="not_loaded_yet",
        random_seed=config.project.random_seed,
        python_version=sys_meta.get("python_version"),
        git_commit=sys_meta.get("git_commit"),
        git_dirty=sys_meta.get("git_dirty"),
    )
