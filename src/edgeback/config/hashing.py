"""Configuration identity helpers."""

from __future__ import annotations

from edgeback.config.models import ResolvedConfig
from edgeback.utils import stable_hash


def config_hash(config: ResolvedConfig) -> str:
    payload = config.model_dump(mode="json", exclude={"resolution"})
    return stable_hash(payload)


def simulation_hash(config: ResolvedConfig) -> str:
    payload = config.model_dump(mode="json", exclude={"report", "resolution"})
    return stable_hash(payload)
