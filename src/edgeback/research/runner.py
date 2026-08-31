"""Deterministic research orchestration for sweeps and walk-forward evaluation."""

from __future__ import annotations

import itertools
import json
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from edgeback.artifacts import RunArtifactWriter, canonical_result_tables
from edgeback.config import load_research_config, resolve_config
from edgeback.config.models import ResearchConfig, ResolvedConfig
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.data.table_io import write_table
from edgeback.domain import Bar, RunStatus
from edgeback.engine import run_backtest
from edgeback.errors import ConfigurationError, SimulationError
from edgeback.metrics import compute_metrics
from edgeback.orchestrator import fixture_manifest, load_backtest_data
from edgeback.research.bootstrap import session_bootstrap
from edgeback.research.gates import evaluate_research_gates
from edgeback.research.robustness import concentration_diagnostics, restress_trade_costs
from edgeback.research.splits import chronological_session_split, walk_forward_folds
from edgeback.utils import stable_hash


def _resolve_base_path(research_path: Path, configured: Path) -> Path:
    if configured.is_absolute():
        return configured
    cwd_candidate = Path.cwd() / configured
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return (research_path.parent / configured).resolve()


def _parameter_combinations(config: ResearchConfig) -> tuple[dict[str, Any], ...]:
    grid = config.research.parameter_grid
    names = sorted(grid)
    combinations = [dict(zip(names, values, strict=True)) for values in itertools.product(*(grid[name] for name in names))]
    if config.research.mode == "random":
        import random

        rng = random.Random(config.research.random_seed)
        rng.shuffle(combinations)
    return tuple(combinations[: config.research.max_trials])


def _with_parameters(base: ResolvedConfig, parameters: dict[str, Any], **overrides: Any) -> ResolvedConfig:
    payload = base.model_dump(mode="json")
    payload["strategy"]["params"] = {**payload["strategy"]["params"], **parameters}
    for dotted_path, value in overrides.items():
        cursor = payload
        parts = dotted_path.split("__")
        for part in parts[:-1]:
            cursor = cursor[part]
        cursor[parts[-1]] = value
    return ResolvedConfig.model_validate(payload)


def _run_window(config: ResolvedConfig, bars: tuple[Bar, ...], sessions: tuple[date, ...]) -> tuple[Any, dict[str, Any], dict[str, pd.DataFrame]]:
    if not sessions:
        raise ConfigurationError("Research evaluation window is empty")
    end = sessions[-1]
    available = tuple(bar for bar in bars if bar.session_date <= end)
    result = run_backtest(config, available, trade_session_dates=set(sessions))
    if result.status is not RunStatus.COMPLETED:
        raise SimulationError(f"Research simulation failed: {result.error_type}: {result.error_message}")
    tables = canonical_result_tables(result)
    metrics = compute_metrics(tables, starting_equity_usd=config.engine.initial_cash_usd)
    return result, metrics, tables


def _metric_for_selection(metrics: dict[str, Any], configured_name: str) -> float:
    key = configured_name
    for prefix in ("validation_", "train_", "test_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
    value = metrics.get(key)
    return float(value) if value is not None else float("-inf")


def _passes_constraints(metrics: dict[str, Any], research: ResearchConfig) -> bool:
    constraints = research.research.selection.constraints
    profit_factor = metrics.get("profit_factor")
    return (
        int(metrics.get("trade_count") or 0) >= constraints.minimum_validation_trades
        and float(metrics.get("max_drawdown_pct") or 0.0) * 100.0 <= constraints.maximum_validation_drawdown_pct
        and profit_factor is not None
        and float(profit_factor) >= constraints.minimum_validation_profit_factor
    )


def _select_trial(records: list[dict[str, Any]], research: ResearchConfig) -> dict[str, Any]:
    eligible = [record for record in records if _passes_constraints(record["validation_metrics"], research)]
    pool = eligible or records
    if not pool:
        raise ConfigurationError("Parameter grid produced no trials")
    primary = research.research.selection.primary_metric

    def key(record: dict[str, Any]) -> tuple[Any, ...]:
        metrics = record["validation_metrics"]
        tie_values: list[float] = []
        for tie in research.research.selection.tie_breakers:
            value = _metric_for_selection(metrics, tie)
            tie_values.append(-value if "drawdown" in tie else value)
        return (_metric_for_selection(metrics, primary), *tie_values, -record["trial_number"])

    selected = max(pool, key=key)
    selected = dict(selected)
    selected["selection_constraints_passed"] = selected in eligible
    return selected


def _atomic_write_directory(
    target: Path,
    files: dict[str, str],
    *,
    tables: dict[str, pd.DataFrame] | None = None,
) -> None:
    """Write a complete immutable research child directory in one rename."""

    if target.exists():
        raise ConfigurationError(f"Research artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        for name, content in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for name, frame in (tables or {}).items():
            table_path = temporary / name
            table_path.parent.mkdir(parents=True, exist_ok=True)
            write_table(frame, table_path)
        os.replace(temporary, target)
    except Exception:
        import shutil

        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _write_research_state(root: Path, state: str, **details: Any) -> None:
    temporary = root / ".RESEARCH_STATE.json.tmp"
    temporary.write_text(
        json.dumps(
            {
                "state": state,
                "updated_at_utc": datetime.now(UTC).isoformat(),
                **details,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, root / "RESEARCH_STATE.json")


def _research_inputs(path: Path, fixture: bool, *, walk_forward: bool = False) -> tuple[ResearchConfig, Path, ResolvedConfig, tuple[Bar, ...], Any]:
    research = load_research_config(path)
    base_path = _resolve_base_path(path, research.research.base_config)
    base = resolve_config(base_path)
    if fixture:
        if walk_forward:
            wf = research.research.walk_forward
            count = wf.train_sessions + wf.validation_sessions + wf.test_sessions + wf.step_sessions * 2
            session_count = max(12, count)
        else:
            session_count = 30
        bars = generate_fixture_bars(
            symbols=base.data.symbols,
            interval_seconds=base.data.interval_seconds,
            session_count=session_count,
        )
        manifest = fixture_manifest(bars)
    else:
        bars, manifest = load_backtest_data(base)
    return research, base_path, base, bars, manifest


def run_research_sweep(config_path: str | Path, *, fixture: bool = False) -> dict[str, Any]:
    path = Path(config_path).resolve()
    research, base_path, base, bars, manifest = _research_inputs(path, fixture)
    sessions = tuple(sorted({bar.session_date for bar in bars}))
    split = chronological_session_split(sessions, research.research.split)
    combinations = _parameter_combinations(research)
    research_identity = stable_hash({
        "research": research.model_dump(mode="json"),
        "data": manifest.get("aggregate_hash") if isinstance(manifest, dict) else manifest.aggregate_hash,
        "sessions": [item.isoformat() for item in sessions],
    })
    research_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}__{research.research.name}__{research_identity[:8]}"
    root = base.report.output_dir / "research" / research_id
    root.mkdir(parents=True, exist_ok=False)
    _write_research_state(
        root,
        "RUNNING",
        research_id=research_id,
        research_identity_hash=research_identity,
    )
    records: list[dict[str, Any]] = []
    for number, parameters in enumerate(combinations, start=1):
        trial_config = _with_parameters(base, parameters)
        _, train_metrics, _ = _run_window(trial_config, bars, split.train)
        _, validation_metrics, validation_tables = _run_window(trial_config, bars, split.validation)
        trial_record = {
            "trial_number": number,
            "trial_id": f"trial-{number:04d}",
            "parameters": parameters,
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "selection_eligible": _passes_constraints(validation_metrics, research),
            "data_hash": manifest.get("aggregate_hash") if isinstance(manifest, dict) else manifest.aggregate_hash,
            "seed": research.research.random_seed,
        }
        trial_dir = root / "trials" / trial_record["trial_id"]
        _atomic_write_directory(
            trial_dir,
            {
                "trial.json": json.dumps(trial_record, indent=2, sort_keys=True, default=str),
                "parameters.json": json.dumps(parameters, indent=2, sort_keys=True, default=str),
            },
            tables={"validation_trades.parquet": validation_tables["trades"]},
        )
        records.append(trial_record)

    selected = _select_trial(records, research)
    selected_config = _with_parameters(base, selected["parameters"])
    final_result, final_metrics, final_tables = _run_window(selected_config, bars, split.test)
    concentration = concentration_diagnostics(final_tables["trades"])
    cost_stress = [
        restress_trade_costs(final_tables["trades"], multiplier)
        for multiplier in research.research.stress.cost_multipliers
    ]
    delay_stress: list[dict[str, Any]] = []
    for delay in research.research.stress.additional_entry_delay_bars:
        stressed_config = _with_parameters(
            selected_config,
            {},
            engine__additional_entry_delay_bars=delay,
        )
        _, metrics, _ = _run_window(stressed_config, bars, split.test)
        delay_stress.append({"additional_entry_delay_bars": delay, "metrics": metrics})
    positive_neighbors = [
        record
        for record in records
        if (record["validation_metrics"].get("expectancy_usd_per_trade") or float("-inf")) > 0
    ]
    parameter_plateau = len(positive_neighbors) >= min(3, len(records))
    robustness = {
        "concentration": concentration,
        "cost_stress": cost_stress,
        "entry_delay_stress": delay_stress,
        "parameter_plateau": parameter_plateau,
        "bootstrap": session_bootstrap(
            final_tables["trades"],
            samples=research.research.stress.bootstrap_sessions,
            seed=research.research.random_seed,
        ),
    }
    gates = evaluate_research_gates(final_metrics, robustness, research.research.gates)
    writer = RunArtifactWriter(base.report.output_dir)
    final_record = writer.write(
        config=selected_config,
        data_manifest=manifest,
        result=final_result,
        conclusion_label=gates["label"],
        gate_results={**gates, "robustness": robustness, "research_id": research_id},
        input_config_path=base_path,
        parent_run_id=research_id,
        fold_id="final-test",
    )
    summary = {
        "research_id": research_id,
        "research_identity_hash": research_identity,
        "trial_count": len(records),
        "split": {
            "train": [item.isoformat() for item in split.train],
            "embargo_train_validation": [item.isoformat() for item in split.embargo_train_validation],
            "validation": [item.isoformat() for item in split.validation],
            "embargo_validation_test": [item.isoformat() for item in split.embargo_validation_test],
            "test": [item.isoformat() for item in split.test],
        },
        "selected_trial": selected,
        "final_test_identity": stable_hash({
            "parameters": selected["parameters"],
            "sessions": [item.isoformat() for item in split.test],
            "data": manifest.get("aggregate_hash") if isinstance(manifest, dict) else manifest.aggregate_hash,
        }),
        "final_metrics": final_metrics,
        "robustness": robustness,
        "gate_results": gates,
        "final_run_id": final_record.run_id,
        "final_run_path": str(final_record.path),
    }
    (root / "research_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    pd.DataFrame.from_records(records).to_json(
        root / "trial_index.json",
        orient="records",
        indent=2,
        default_handler=str,
    )
    _write_research_state(
        root,
        "COMPLETED",
        research_id=research_id,
        research_identity_hash=research_identity,
        trial_count=len(records),
        final_run_id=final_record.run_id,
    )
    return summary


def run_walk_forward_research(config_path: str | Path, *, fixture: bool = False) -> dict[str, Any]:
    path = Path(config_path).resolve()
    research, base_path, base, bars, manifest = _research_inputs(path, fixture, walk_forward=True)
    sessions = tuple(sorted({bar.session_date for bar in bars}))
    folds = walk_forward_folds(sessions, research.research.walk_forward)
    if not folds:
        raise ConfigurationError("No complete walk-forward fold fits the available sessions")
    combinations = _parameter_combinations(research)
    research_identity = stable_hash({
        "research": research.model_dump(mode="json"),
        "data": manifest.get("aggregate_hash") if isinstance(manifest, dict) else manifest.aggregate_hash,
        "mode": "walk_forward",
    })
    research_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}__{research.research.name}__wf__{research_identity[:8]}"
    root = base.report.output_dir / "research" / research_id
    root.mkdir(parents=True, exist_ok=False)
    _write_research_state(
        root,
        "RUNNING",
        research_id=research_id,
        research_identity_hash=research_identity,
    )
    writer = RunArtifactWriter(base.report.output_dir)
    fold_records: list[dict[str, Any]] = []
    aggregate_trades: list[pd.DataFrame] = []
    aggregate_fills: list[pd.DataFrame] = []
    for fold in folds:
        candidates: list[dict[str, Any]] = []
        for number, parameters in enumerate(combinations, start=1):
            trial_config = _with_parameters(base, parameters)
            _, train_metrics, _ = _run_window(trial_config, bars, fold.train)
            _, validation_metrics, _ = _run_window(trial_config, bars, fold.validation)
            candidates.append({
                "trial_number": number,
                "parameters": parameters,
                "train_metrics": train_metrics,
                "validation_metrics": validation_metrics,
            })
        selected = _select_trial(candidates, research)
        selected_config = _with_parameters(base, selected["parameters"])
        test_result, test_metrics, test_tables = _run_window(selected_config, bars, fold.test)
        aggregate_trades.append(test_tables["trades"])
        aggregate_fills.append(test_tables["fills"])
        run_record = writer.write(
            config=selected_config,
            data_manifest=manifest,
            result=test_result,
            conclusion_label="OOS_PROMISING_NOT_ROBUST" if (test_metrics.get("expectancy_usd_per_trade") or 0) > 0 else "OOS_FAILED",
            gate_results={"label": "FOLD_OOS", "gates": [], "fold_id": fold.fold_id},
            input_config_path=base_path,
            parent_run_id=research_id,
            fold_id=fold.fold_id,
        )
        fold_record = {
            "fold_id": fold.fold_id,
            "train_sessions": [item.isoformat() for item in fold.train],
            "validation_sessions": [item.isoformat() for item in fold.validation],
            "test_sessions": [item.isoformat() for item in fold.test],
            "selected": selected,
            "test_metrics": test_metrics,
            "run_id": run_record.run_id,
            "run_path": str(run_record.path),
        }
        fold_records.append(fold_record)
        fold_dir = root / "folds" / fold.fold_id
        _atomic_write_directory(
            fold_dir,
            {"fold.json": json.dumps(fold_record, indent=2, sort_keys=True, default=str)},
        )

    combined_trades = pd.concat(aggregate_trades, ignore_index=True) if aggregate_trades else pd.DataFrame()
    combined_fills = pd.concat(aggregate_fills, ignore_index=True) if aggregate_fills else pd.DataFrame()
    # Aggregate OOS metrics that are meaningful across independently reset folds.
    if combined_trades.empty:
        aggregate_metrics = {"trade_count": 0, "net_pnl_usd": 0.0, "expectancy_usd_per_trade": None, "profit_factor": None}
    else:
        wins = combined_trades.loc[combined_trades["net_pnl_usd"] > 0, "net_pnl_usd"].astype(float)
        losses = combined_trades.loc[combined_trades["net_pnl_usd"] < 0, "net_pnl_usd"].astype(float)
        aggregate_metrics = {
            "trade_count": int(len(combined_trades)),
            "net_pnl_usd": float(combined_trades["net_pnl_usd"].sum()),
            "expectancy_usd_per_trade": float(combined_trades["net_pnl_usd"].mean()),
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else None,
        }
    concentration = concentration_diagnostics(combined_trades)
    cost_stress = [restress_trade_costs(combined_trades, multiplier) for multiplier in research.research.stress.cost_multipliers]
    robustness = {
        "concentration": concentration,
        "cost_stress": cost_stress,
        "parameter_plateau": len({json.dumps(item["selected"]["parameters"], sort_keys=True) for item in fold_records}) <= max(1, len(fold_records)),
        "bootstrap": session_bootstrap(
            combined_trades,
            samples=research.research.stress.bootstrap_sessions,
            seed=research.research.random_seed,
        ),
    }
    gates = evaluate_research_gates(aggregate_metrics, robustness, research.research.gates)
    summary = {
        "research_id": research_id,
        "research_identity_hash": research_identity,
        "fold_count": len(fold_records),
        "folds": fold_records,
        "aggregate_oos_metrics": aggregate_metrics,
        "robustness": robustness,
        "gate_results": gates,
    }
    (root / "walk_forward_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    write_table(combined_trades, root / "walk_forward_trades.parquet")
    write_table(combined_fills, root / "walk_forward_fills.parquet")
    _write_research_state(
        root,
        "COMPLETED",
        research_id=research_id,
        research_identity_hash=research_identity,
        fold_count=len(fold_records),
    )
    return summary
