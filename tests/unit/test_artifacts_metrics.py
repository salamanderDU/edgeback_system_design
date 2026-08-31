from __future__ import annotations

import json
from pathlib import Path

from edgeback.artifacts import RunArtifactWriter, RunRegistry, canonical_result_tables, validate_table_linkage
from edgeback.config import resolve_config
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.engine import run_backtest
from edgeback.metrics import compute_metrics

ROOT = Path(__file__).resolve().parents[2]


def _fixture_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_id": "fixture-dataset",
        "provider": "fixture",
        "feed": "fixture",
        "interval_seconds": 300,
        "adjustment_mode": "split_adjusted",
        "aggregate_hash": "fixture-hash",
        "validation": {"status": "PASS", "overall_completeness_pct": 100.0, "excluded_sessions": []},
        "capability_snapshot": {"limitations": ["Synthetic fixture data"]},
        "licensing_warning": "Fixture only",
    }


def test_tables_metrics_and_linkage() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    tables = canonical_result_tables(result)
    assert not validate_table_linkage(tables)
    assert set(tables) == {"intents", "decisions", "orders", "order_events", "fills", "trades", "equity", "warnings"}
    assert {"spread_cost_usd", "slippage_cost_usd", "commission_usd"}.issubset(tables["fills"].columns)
    metrics = compute_metrics(tables, starting_equity_usd=config.engine.initial_cash_usd)
    assert metrics["trade_count"] == 2
    assert metrics["ending_equity_usd"] > config.engine.initial_cash_usd
    assert metrics["total_costs_usd"] > 0


def test_zero_trade_metrics_explain_undefined() -> None:
    config = resolve_config(
        ROOT / "configs/example_backtest.yaml",
        symbols=["AAA"],
        params=["close_if_not_triggered_by=09:45"],
    )
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    metrics = compute_metrics(canonical_result_tables(result), starting_equity_usd=100_000.0)
    assert metrics["trade_count"] == 0
    assert metrics["profit_factor"] is None
    assert "profit_factor" in metrics["undefined_reasons"]


def test_atomic_writer_registry_and_required_files(tmp_path: Path) -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    writer = RunArtifactWriter(tmp_path / "runs")
    record = writer.write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
        input_config_path=ROOT / "configs/example_backtest.yaml",
    )
    required = {
        "RUN_STATE.json", "config.input.yaml", "config.resolved.yaml", "run_metadata.json",
        "data_manifest.json", "warnings.json", "logs.jsonl", "intents.parquet", "orders.parquet",
        "fills.parquet", "trades.parquet", "equity.parquet", "daily_returns.parquet",
        "metrics.json", "gate_results.json", "report.html",
    }
    assert required.issubset({path.name for path in record.path.iterdir()})
    assert json.loads((record.path / "RUN_STATE.json").read_text())["state"] == "COMPLETED"
    registry = RunRegistry(tmp_path / "runs" / "registry.sqlite3")
    assert registry.get(record.run_id).path == record.path
    assert "EdgeBack" in (record.path / "report.html").read_text()


def test_run_verifier_detects_tampering(tmp_path: Path) -> None:
    import pytest

    from edgeback.artifacts import verify_run_directory
    from edgeback.errors import ArtifactError

    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    record = RunArtifactWriter(tmp_path / "runs").write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
    )
    assert verify_run_directory(record.path)["verified"] is True
    metrics_path = record.path / "metrics.json"
    metrics_path.write_text(metrics_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ArtifactError):
        verify_run_directory(record.path)


def test_identical_runs_have_identical_canonical_outputs(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from edgeback.utils import file_sha256

    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = generate_fixture_bars(symbols=("AAA",), session_count=3)
    first_result = run_backtest(config, bars)
    second_result = run_backtest(config, bars)
    first = RunArtifactWriter(tmp_path / "runs_one").write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=first_result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
        started_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = RunArtifactWriter(tmp_path / "runs_two").write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=second_result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
        started_at_utc=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1),
    )
    for name in (
        "intents.parquet",
        "orders.parquet",
        "fills.parquet",
        "trades.parquet",
        "equity.parquet",
        "metrics.json",
        "gate_results.json",
    ):
        assert file_sha256(first.path / name) == file_sha256(second.path / name)


def test_completed_run_cannot_be_overwritten(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    import pytest

    from edgeback.errors import ArtifactError

    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    writer = RunArtifactWriter(tmp_path / "runs")
    started = datetime(2026, 1, 1, tzinfo=UTC)
    writer.write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
        started_at_utc=started,
    )
    with pytest.raises(ArtifactError, match="Refusing to overwrite"):
        writer.write(
            config=config,
            data_manifest=_fixture_manifest(),
            result=result,
            conclusion_label="ENGINE_VALIDATION_ONLY",
            started_at_utc=started,
        )


def test_failed_run_preserves_state_logs_and_traceback(tmp_path: Path) -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = list(generate_fixture_bars(symbols=("AAA",), session_count=1))
    bars.reverse()
    result = run_backtest(config, bars)
    record = RunArtifactWriter(tmp_path / "runs").write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
    )
    assert json.loads((record.path / "RUN_STATE.json").read_text())["state"] == "FAILED"
    assert (record.path / "logs.jsonl").exists()
    assert (record.path / "failure_traceback.txt").read_text(encoding="utf-8")


def test_run_folder_remains_verifiable_without_registry(tmp_path: Path) -> None:
    from edgeback.artifacts import verify_run_directory

    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    result = run_backtest(config, generate_fixture_bars(symbols=("AAA",), session_count=3))
    runs_root = tmp_path / "runs"
    record = RunArtifactWriter(runs_root).write(
        config=config,
        data_manifest=_fixture_manifest(),
        result=result,
        conclusion_label="ENGINE_VALIDATION_ONLY",
    )
    (runs_root / "registry.sqlite3").unlink()
    assert verify_run_directory(record.path)["verified"] is True
