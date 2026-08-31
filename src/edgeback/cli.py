"""Typer command-line interface for EdgeBack."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from edgeback import __version__
from edgeback.artifacts import RunRegistry
from edgeback.calendar import XNYSCalendar
from edgeback.config import resolve_config
from edgeback.config.models import ResolvedConfig
from edgeback.data import DataRepository, acquire_and_ingest, bars_to_frame, provider_capabilities, validate_bars
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.data.providers import LocalFileProvider, ProviderCapabilities
from edgeback.data.table_io import parquet_available, read_table
from edgeback.errors import EdgeBackError, ExitCode
from edgeback.orchestrator import execute_backtest, load_backtest_data
from edgeback.reporting import render_html_report
from edgeback.strategy import describe_strategy, list_strategies
from edgeback.utils import ensure_writable_directory, env_present, package_versions, redact

app = typer.Typer(name="edgeback", help="Deterministic intraday backtesting and edge research.", no_args_is_help=True)
strategies_app = typer.Typer(help="Inspect trusted strategy plugins.", no_args_is_help=True)
data_app = typer.Typer(help="Acquire, import, validate, and list canonical data.", no_args_is_help=True)
backtest_app = typer.Typer(help="Run offline deterministic simulations.", no_args_is_help=True)
runs_app = typer.Typer(help="Inspect immutable run records.", no_args_is_help=True)
report_app = typer.Typer(help="Build derived reports without mutating completed runs.", no_args_is_help=True)
research_app = typer.Typer(help="Run sweeps, walk-forward analysis, and robustness checks.", no_args_is_help=True)
app.add_typer(strategies_app, name="strategies")
app.add_typer(data_app, name="data")
app.add_typer(backtest_app, name="backtest")
app.add_typer(runs_app, name="runs")
app.add_typer(report_app, name="report")
app.add_typer(research_app, name="research")


def _json_echo(value: Any) -> None:
    typer.echo(json.dumps(redact(value), indent=2, sort_keys=True, default=str))


def _abort(exc: Exception) -> None:
    if isinstance(exc, EdgeBackError):
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(int(exc.exit_code)) from exc
    typer.echo(f"ERROR: {type(exc).__name__}: {exc}", err=True)
    raise typer.Exit(int(ExitCode.SIMULATION_FAILED)) from exc


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the installed version and exit.", is_eager=True)] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def doctor(
    config: Annotated[Path, typer.Option("--config", "-c", help="Config to validate.")] = Path("configs/example_backtest.yaml"),
) -> None:
    """Check the offline runtime, config, writable paths, and fixture engine."""
    try:
        resolved = resolve_config(config)
        ensure_writable_directory(resolved.data.cache_dir)
        ensure_writable_directory(resolved.report.output_dir)
        bars = generate_fixture_bars(
            symbols=resolved.data.symbols,
            interval_seconds=resolved.data.interval_seconds,
            session_count=3,
        )
        from edgeback.engine import run_backtest

        result = run_backtest(resolved, bars)
        payload = {
            "status": "PASS" if result.status.value == "COMPLETED" else "FAIL",
            "edgeback_version": __version__,
            "python": platform.python_version(),
            "python_supported": sys.version_info >= (3, 12),
            "dependencies": package_versions(
                ("pydantic", "pandas", "pyarrow", "PyYAML", "typer", "exchange-calendars")
            ),
            "parquet_backend": "pyarrow" if parquet_available() else "explicit_test_fallback",
            "fixture": {
                "bars": len(bars),
                "trades": len(result.trades),
                "reconciled": result.reconciliation.get("reconciled"),
            },
            "provider_auth": {
                "alpaca": {
                    "configured": env_present("ALPACA_API_KEY") and env_present("ALPACA_SECRET_KEY"),
                    "field_count_present": int(env_present("ALPACA_API_KEY")) + int(env_present("ALPACA_SECRET_KEY")),
                }
            },
            "notes": [
                "Provider credentials are reported only as present/absent; values are never printed.",
                "Network provider smoke tests are not part of doctor.",
            ],
        }
        _json_echo(payload)
        if payload["status"] != "PASS" or not payload["python_supported"]:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@strategies_app.command("list")
def strategies_list() -> None:
    try:
        _json_echo(list_strategies())
    except Exception as exc:
        _abort(exc)


@strategies_app.command("describe")
def strategies_describe(strategy_id: str) -> None:
    try:
        _json_echo(describe_strategy(strategy_id))
    except Exception as exc:
        _abort(exc)


@data_app.command("providers")
def data_providers() -> None:
    _json_echo(provider_capabilities())


@data_app.command("download")
def data_download(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    symbol: Annotated[list[str] | None, typer.Option("--symbol", help="Replace data.symbols; repeatable.")] = None,
) -> None:
    try:
        resolved = resolve_config(config, symbols=symbol)
        manifest = acquire_and_ingest(resolved)
        _json_echo({"dataset_id": manifest.dataset_id, "manifest": str(resolved.data.cache_dir / "manifests" / f"{manifest.dataset_id}.json")})
    except Exception as exc:
        _abort(exc)


@data_app.command("import")
def data_import(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    file: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False)],
    symbol: Annotated[str, typer.Option("--symbol")],
    timestamp_column: Annotated[str, typer.Option("--timestamp-column")] = "timestamp",
    timestamp_semantics: Annotated[str, typer.Option("--timestamp-semantics")] = "bar_start",
    source_timezone: Annotated[str, typer.Option("--source-timezone")] = "UTC",
    feed: Annotated[str, typer.Option("--feed")] = "local",
    column_map: Annotated[list[str] | None, typer.Option("--column-map", help="source=canonical; repeatable")] = None,
) -> None:
    try:
        resolved = resolve_config(config, symbols=[symbol], sets=["data.provider=local", f"data.feed={feed}"])
        mapping: dict[str, str] = {}
        for item in column_map or []:
            if "=" not in item:
                raise ValueError("--column-map requires source=canonical")
            source, target = item.split("=", 1)
            mapping[source] = target
        bars = LocalFileProvider().import_file(
            file,
            symbol=symbol,
            interval_seconds=resolved.data.interval_seconds,
            timestamp_column=timestamp_column,
            timestamp_semantics=timestamp_semantics,
            source_timezone=source_timezone,
            feed=feed,
            adjustment_mode=resolved.data.adjustment_mode,
            column_map=mapping,
        )
        capabilities = ProviderCapabilities(
            provider_id="local",
            feeds=(feed,),
            intervals=(resolved.data.interval,),
            limitations=("Quality, licensing, timestamp semantics, and adjustments are user-supplied.",),
        )
        manifest = DataRepository(resolved.data.cache_dir).ingest(
            bars,
            calendar=XNYSCalendar(),
            capabilities=capabilities,
            minimum_session_completeness_pct=resolved.data.minimum_session_completeness_pct,
            missing_session_policy=resolved.data.missing_session_policy,
            licensing_warning="User-supplied local file; user is responsible for data rights and provenance.",
        )
        _json_echo({"dataset_id": manifest.dataset_id, "rows": sum(manifest.row_counts.values())})
    except Exception as exc:
        _abort(exc)


@data_app.command("validate")
def data_validate(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    fixture: Annotated[bool, typer.Option("--fixture", help="Validate deterministic local fixture data.")] = False,
    symbol: Annotated[list[str] | None, typer.Option("--symbol")] = None,
) -> None:
    try:
        resolved = resolve_config(config, symbols=symbol)
        if fixture:
            bars = generate_fixture_bars(
                symbols=resolved.data.symbols,
                interval_seconds=resolved.data.interval_seconds,
                session_count=3,
            )
            report = validate_bars(
                bars_to_frame(bars),
                calendar=XNYSCalendar(),
                minimum_session_completeness_pct=100.0,
                missing_session_policy="fail_dataset",
            )
        else:
            bars, manifest = load_backtest_data(resolved)
            report = validate_bars(
                bars_to_frame(bars),
                calendar=XNYSCalendar(),
                minimum_session_completeness_pct=resolved.data.minimum_session_completeness_pct,
                missing_session_policy=resolved.data.missing_session_policy,
            )
            _ = manifest
        _json_echo(report.model_dump(mode="json"))
        if not report.passed:
            raise typer.Exit(int(ExitCode.DATA_VALIDATION_FAILED))
    except typer.Exit:
        raise
    except Exception as exc:
        _abort(exc)


@data_app.command("list")
def data_list(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("data"),
) -> None:
    try:
        manifests = DataRepository(data_dir).list_manifests()
        _json_echo([
            {
                "dataset_id": item.dataset_id,
                "provider": item.provider,
                "feed": item.feed,
                "symbols": sorted(item.canonical_to_provider_symbols),
                "interval_seconds": item.interval_seconds,
                "rows": sum(item.row_counts.values()),
                "validation": item.validation.status.value,
            }
            for item in manifests
        ])
    except Exception as exc:
        _abort(exc)


@backtest_app.command("run")
def backtest_run(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    symbol: Annotated[list[str] | None, typer.Option("--symbol", help="Replace symbols; repeatable.")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", help="Strategy name=value; repeatable.")] = None,
    set_value: Annotated[list[str] | None, typer.Option("--set", help="Typed dotted path=value; repeatable.")] = None,
    fixture: Annotated[bool, typer.Option("--fixture")] = False,
) -> None:
    try:
        resolved = resolve_config(config, symbols=symbol, params=param or [], sets=set_value or [])
        record = execute_backtest(resolved, fixture=fixture, input_config_path=config)
        typer.echo(str(record.path))
    except Exception as exc:
        _abort(exc)


@backtest_app.command("batch")
def backtest_batch(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    symbol: Annotated[list[str] | None, typer.Option("--symbol")] = None,
    fixture: Annotated[bool, typer.Option("--fixture")] = False,
) -> None:
    try:
        base = resolve_config(config, symbols=symbol)
        paths: list[str] = []
        for item in base.data.symbols:
            resolved = resolve_config(config, symbols=[item])
            paths.append(str(execute_backtest(resolved, fixture=fixture, input_config_path=config).path))
        _json_echo(paths)
    except Exception as exc:
        _abort(exc)


@runs_app.command("list")
def runs_list(
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("runs"),
    limit: Annotated[int, typer.Option("--limit", min=1, max=10000)] = 100,
) -> None:
    try:
        _json_echo([item.model_dump(mode="json") for item in RunRegistry(output_dir / "registry.sqlite3").list(limit=limit)])
    except Exception as exc:
        _abort(exc)


@runs_app.command("show")
def runs_show(
    run_id: str,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("runs"),
) -> None:
    try:
        record = RunRegistry(output_dir / "registry.sqlite3").get(run_id)
        metadata = json.loads((record.path / "run_metadata.json").read_text(encoding="utf-8"))
        _json_echo({"record": record.model_dump(mode="json"), "metadata": metadata})
    except Exception as exc:
        _abort(exc)


@report_app.command("build")
def report_build(
    run_id: str,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("runs"),
) -> None:
    try:
        record = RunRegistry(output_dir / "registry.sqlite3").get(run_id)
        run_dir = record.path
        config_payload = yaml.safe_load((run_dir / "config.resolved.yaml").read_text(encoding="utf-8"))
        config = ResolvedConfig.model_validate(config_payload)
        metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        gates = json.loads((run_dir / "gate_results.json").read_text(encoding="utf-8"))
        tables = {
            name: read_table(run_dir / f"{name}.parquet")
            for name in ("intents", "decisions", "orders", "order_events", "fills", "trades", "equity", "warnings")
        }
        rendered = render_html_report(
            metadata=metadata,
            config=config,
            data_manifest=manifest,
            metrics=metrics,
            tables=tables,
            gate_results=gates,
        )
        derived_dir = output_dir / "derived_reports"
        derived_dir.mkdir(parents=True, exist_ok=True)
        target = derived_dir / f"{run_id}.html"
        target.write_text(rendered, encoding="utf-8")
        typer.echo(str(target))
    except Exception as exc:
        _abort(exc)


# Research commands import lazily to keep normal CLI startup small.
@research_app.command("sweep")
def research_sweep(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    fixture: Annotated[bool, typer.Option("--fixture")] = False,
) -> None:
    try:
        from edgeback.research.runner import run_research_sweep

        _json_echo(run_research_sweep(config, fixture=fixture))
    except Exception as exc:
        _abort(exc)


@research_app.command("walk-forward")
def research_walk_forward(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    fixture: Annotated[bool, typer.Option("--fixture")] = False,
) -> None:
    try:
        from edgeback.research.runner import run_walk_forward_research

        _json_echo(run_walk_forward_research(config, fixture=fixture))
    except Exception as exc:
        _abort(exc)


if __name__ == "__main__":
    app()
