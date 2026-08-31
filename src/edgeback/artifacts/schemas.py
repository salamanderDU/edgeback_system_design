"""Runtime validation models for required artifact metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConclusionLabel = Literal[
    "ENGINE_VALIDATION_ONLY",
    "INSUFFICIENT_EVIDENCE",
    "IN_SAMPLE_ONLY",
    "OOS_FAILED",
    "OOS_PROMISING_NOT_ROBUST",
    "ROBUST_ON_TESTED_DATA",
]


class _ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class StrategyIdentity(_ArtifactModel):
    id: str
    version: str | None = None
    parameters: dict[str, Any]


class RunMetadata(_ArtifactModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    research_id: str | None = None
    trial_id: str | None = None
    parent_run_id: str | None = None
    fold_id: str | None = None
    status: Literal["CREATED", "RUNNING", "COMPLETED", "FAILED"]
    started_at_utc: datetime
    finished_at_utc: datetime
    duration_seconds: float = Field(ge=0)
    strategy: StrategyIdentity
    config_hash: str
    data_manifest_hash: str
    strategy_id: str
    strategy_version: str | None = None
    strategy_params_hash: str
    engine_version: str
    seed: int
    execution_model: dict[str, Any]
    logical_identity_hash: str
    code: dict[str, Any]
    runtime: dict[str, Any]
    artifact_checksums: dict[str, str]
    conclusion_label: ConclusionLabel
