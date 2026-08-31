from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from edgeback.artifacts import RunArtifactWriter
from edgeback.config import resolve_config
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.engine import run_backtest
from edgeback.orchestrator import fixture_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_bar_and_run_metadata_schemas_are_valid_json_schema(tmp_path: Path) -> None:
    bar_schema = json.loads((ROOT / "schemas/bar.schema.json").read_text())
    metadata_schema = json.loads((ROOT / "schemas/run_metadata.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(bar_schema)
    jsonschema.Draft202012Validator.check_schema(metadata_schema)

    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = generate_fixture_bars(symbols=("AAA",), session_count=3)
    result = run_backtest(config, bars)
    record = RunArtifactWriter(tmp_path / "runs").write(
        config=config,
        data_manifest=fixture_manifest(bars),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
    )
    metadata = json.loads((record.path / "run_metadata.json").read_text())
    jsonschema.validate(metadata, metadata_schema, format_checker=jsonschema.FormatChecker())
    jsonschema.validate(bars[0].model_dump(mode="json"), bar_schema, format_checker=jsonschema.FormatChecker())
