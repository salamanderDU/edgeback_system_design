from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from edgeback.cli import app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def _config(tmp_path: Path) -> Path:
    payload = yaml.safe_load((ROOT / "configs/example_backtest.yaml").read_text())
    payload["data"]["symbols"] = ["AAA", "BBB"]
    payload["data"]["cache_dir"] = str(tmp_path / "data")
    payload["report"]["output_dir"] = str(tmp_path / "runs")
    target = tmp_path / "config.yaml"
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return target


def test_cli_offline_acceptance_surface(tmp_path: Path) -> None:
    config = _config(tmp_path)
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert "0.1.0" in version.stdout

    doctor = runner.invoke(app, ["doctor", "-c", str(config)])
    assert doctor.exit_code == 0, doctor.stdout
    assert json.loads(doctor.stdout)["status"] == "PASS"

    listed = runner.invoke(app, ["strategies", "list"])
    assert listed.exit_code == 0
    assert "opening_range_breakout" in listed.stdout

    providers = runner.invoke(app, ["data", "providers"])
    assert providers.exit_code == 0
    assert {item["provider_id"] for item in json.loads(providers.stdout)} == {
        "yfinance",
        "alpaca",
        "local",
    }

    validation = runner.invoke(app, ["data", "validate", "-c", str(config), "--fixture"])
    assert validation.exit_code == 0, validation.stdout
    assert json.loads(validation.stdout)["status"] == "PASS"

    run = runner.invoke(app, ["backtest", "run", "-c", str(config), "--fixture"])
    assert run.exit_code == 0, run.stdout
    run_path = Path(run.stdout.strip())
    assert run_path.exists()
    run_id = run_path.name

    runs = runner.invoke(app, ["runs", "list", "--output-dir", str(tmp_path / "runs")])
    assert runs.exit_code == 0
    assert run_id in runs.stdout

    before = {
        path.name: path.read_bytes()
        for path in run_path.iterdir()
        if path.is_file()
    }
    rebuilt = runner.invoke(
        app,
        ["report", "build", run_id, "--output-dir", str(tmp_path / "runs")],
    )
    assert rebuilt.exit_code == 0, rebuilt.stdout
    assert Path(rebuilt.stdout.strip()).exists()
    after = {
        path.name: path.read_bytes()
        for path in run_path.iterdir()
        if path.is_file()
    }
    assert after == before


def test_cli_symbol_override_does_not_edit_strategy(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = runner.invoke(
        app,
        ["backtest", "run", "-c", str(config), "--symbol", "ZZZ", "--fixture"],
    )
    assert result.exit_code == 0, result.stdout
    resolved = yaml.safe_load((Path(result.stdout.strip()) / "config.resolved.yaml").read_text())
    assert resolved["data"]["symbols"] == ["ZZZ"]
