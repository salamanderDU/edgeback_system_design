"""Application services joining config, data, engine, and artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edgeback.artifacts import RunArtifactWriter, RunRecord
from edgeback.calendar import XNYSCalendar
from edgeback.config.models import ResolvedConfig
from edgeback.data import DataRepository, bars_to_frame, validate_bars
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.domain import Bar, RunStatus
from edgeback.engine import run_backtest
from edgeback.errors import DataUnavailableError, SimulationError
from edgeback.utils import stable_hash


def fixture_manifest(bars: tuple[Bar, ...]) -> dict[str, Any]:
    frame = bars_to_frame(bars)
    report = validate_bars(
        frame,
        calendar=XNYSCalendar(),
        minimum_session_completeness_pct=100.0,
        missing_session_policy="fail_dataset",
        now=datetime(2262, 1, 1, tzinfo=UTC),
    )
    identity = frame.copy()
    identity["ingested_at_utc"] = "<fixture>"
    aggregate = stable_hash(identity.to_dict(orient="records"))
    return {
        "schema_version": "1.0",
        "dataset_id": f"fixture-{aggregate[:16]}",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "provider": "fixture",
        "feed": "fixture",
        "capability_snapshot": {
            "provider_id": "fixture",
            "feeds": ["fixture"],
            "intervals": [f"{bars[0].interval_seconds // 60}m"],
            "limitations": ["Deterministic synthetic bars for engine validation only."],
        },
        "canonical_to_provider_symbols": {symbol: symbol for symbol in sorted(frame["symbol"].unique())},
        "interval_seconds": bars[0].interval_seconds,
        "actual_start_utc": bars[0].bar_start_utc.isoformat(),
        "actual_end_utc": bars[-1].bar_end_utc.isoformat(),
        "session_types": sorted(frame["session_type"].unique().tolist()),
        "calendar_id": "XNYS",
        "adjustment_mode": "split_adjusted",
        "row_counts": frame.groupby("symbol").size().to_dict(),
        "validation": report.model_dump(mode="json"),
        "partitions": [],
        "aggregate_hash": aggregate,
        "raw_request_ids": [],
        "ingestion_version": "fixture",
        "licensing_warning": "Synthetic fixture; not market data.",
    }


def load_backtest_data(config: ResolvedConfig, *, fixture: bool = False) -> tuple[tuple[Bar, ...], Any]:
    if fixture:
        bars = generate_fixture_bars(
            symbols=config.data.symbols,
            interval_seconds=config.data.interval_seconds,
            session_count=3,
        )
        return bars, fixture_manifest(bars)
    repository = DataRepository(config.data.cache_dir)
    if config.data.dataset_id:
        manifest = repository.load_manifest(config.data.dataset_id)
    else:
        manifest = repository.find_compatible(
            provider=config.data.provider,
            feed=config.data.feed,
            symbols=config.data.symbols,
            interval_seconds=config.data.interval_seconds,
        )
    configured_start = config.data.date_range.start
    configured_end = config.data.date_range.end
    if configured_start is not None and manifest.actual_start_utc.date() > configured_start:
        raise DataUnavailableError("Canonical dataset does not cover the configured start date")
    if configured_end is not None and manifest.actual_end_utc.date() < configured_end:
        raise DataUnavailableError("Canonical dataset does not cover the configured end date")
    bars = tuple(
        bar
        for bar in repository.load_bars(manifest.dataset_id)
        if bar.symbol in config.data.symbols
        and (configured_start is None or bar.session_date >= configured_start)
        and (configured_end is None or bar.session_date <= configured_end)
    )
    if not bars:
        raise DataUnavailableError("Compatible dataset has no bars inside the resolved date range")
    return bars, manifest


def execute_backtest(
    config: ResolvedConfig,
    *,
    fixture: bool = False,
    input_config_path: str | Path | None = None,
    trade_session_dates: set[Any] | None = None,
    conclusion_label: str | None = None,
    gate_results: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
    fold_id: str | None = None,
) -> RunRecord:
    bars, manifest = load_backtest_data(config, fixture=fixture)
    started = datetime.now(UTC)
    result = run_backtest(config, bars, trade_session_dates=trade_session_dates)
    label = conclusion_label or ("ENGINE_VALIDATION_ONLY" if fixture else "IN_SAMPLE_ONLY")
    writer = RunArtifactWriter(config.report.output_dir)
    record = writer.write(
        config=config,
        data_manifest=manifest,
        result=result,
        conclusion_label=label,
        gate_results=gate_results,
        input_config_path=input_config_path,
        parent_run_id=parent_run_id,
        fold_id=fold_id,
        started_at_utc=started,
    )
    if result.status is not RunStatus.COMPLETED:
        raise SimulationError(
            f"Simulation failed; diagnostics preserved at {record.path}: {result.error_type}: {result.error_message}"
        )
    return record
