from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from edgeback.config.models import GateConfig, SplitConfig, WalkForwardConfig
from edgeback.research import chronological_session_split, evaluate_research_gates, walk_forward_folds
from edgeback.research.runner import run_research_sweep

ROOT = Path(__file__).resolve().parents[2]


def test_chronological_split_and_walk_forward_never_overlap() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(20))
    split = chronological_session_split(
        sessions,
        SplitConfig(train_pct=50, validation_pct=25, test_pct=25, embargo_sessions=1),
    )
    assert set(split.train).isdisjoint(split.validation)
    assert set(split.validation).isdisjoint(split.test)
    assert max(split.train) < min(split.validation) < min(split.test)
    folds = walk_forward_folds(
        sessions,
        WalkForwardConfig(method="rolling", train_sessions=8, validation_sessions=2, test_sessions=2, step_sessions=2),
    )
    assert folds
    assert all(max(fold.train) < min(fold.validation) < min(fold.test) for fold in folds)


def test_gate_labels_are_constrained() -> None:
    result = evaluate_research_gates(
        {"expectancy_usd_per_trade": 5.0, "trade_count": 10},
        {
            "concentration": {"single_trade_profit_contribution_pct": 10.0, "single_session_profit_contribution_pct": 20.0},
            "cost_stress": [{"cost_multiplier": 2.0, "net_pnl_usd": 1.0}],
            "parameter_plateau": True,
        },
        GateConfig(minimum_oos_trades=5),
    )
    assert result["label"] == "ROBUST_ON_TESTED_DATA"


def test_small_fixture_sweep_persists_all_trials(tmp_path: Path) -> None:
    base_payload = yaml.safe_load((ROOT / "configs/example_backtest.yaml").read_text())
    base_payload["data"]["symbols"] = ["AAA"]
    base_payload["report"]["output_dir"] = str(tmp_path / "runs")
    base = tmp_path / "base.yaml"
    base.write_text(yaml.safe_dump(base_payload), encoding="utf-8")
    research_payload = {
        "config_version": "1.0",
        "research": {
            "name": "tiny_sweep",
            "base_config": str(base),
            "random_seed": 7,
            "mode": "grid",
            "max_trials": 2,
            "split": {
                "method": "chronological_sessions",
                "train_pct": 50.0,
                "validation_pct": 25.0,
                "test_pct": 25.0,
                "embargo_sessions": 1,
                "final_test_immutable": True,
            },
            "selection": {
                "primary_metric": "validation_expectancy_usd_per_trade",
                "tie_breakers": ["validation_max_drawdown_pct"],
                "constraints": {
                    "minimum_validation_trades": 0,
                    "maximum_validation_drawdown_pct": 100.0,
                    "minimum_validation_profit_factor": 0.0,
                },
            },
            "parameter_grid": {"breakout_buffer_bps": [0.0, 5.0]},
            "walk_forward": {
                "enabled": True,
                "method": "rolling",
                "train_sessions": 6,
                "validation_sessions": 2,
                "test_sessions": 2,
                "step_sessions": 2,
            },
            "stress": {
                "cost_multipliers": [1.0, 2.0],
                "additional_entry_delay_bars": [0, 1],
                "remove_best_trade": True,
                "remove_best_session": True,
                "parameter_neighborhood": True,
                "bootstrap_sessions": 20,
            },
            "gates": {
                "minimum_oos_trades": 1,
                "maximum_single_trade_profit_contribution_pct": 100.0,
                "maximum_single_session_profit_contribution_pct": 100.0,
                "require_nonnegative_at_2x_cost": False,
                "require_parameter_plateau": False,
            },
        },
    }
    research_path = tmp_path / "research.yaml"
    research_path.write_text(yaml.safe_dump(research_payload), encoding="utf-8")
    summary = run_research_sweep(research_path, fixture=True)
    assert summary["trial_count"] == 2
    research_dir = tmp_path / "runs" / "research" / summary["research_id"]
    assert len(list((research_dir / "trials").glob("trial-*"))) == 2
    assert all(
        (trial / "validation_trades.parquet").exists()
        for trial in (research_dir / "trials").glob("trial-*")
    )
    assert yaml.safe_load((research_dir / "RESEARCH_STATE.json").read_text())["state"] == "COMPLETED"
    assert not list((research_dir / "trials").glob(".trial-*-*"))
    assert Path(summary["final_run_path"]).exists()


def test_small_walk_forward_selects_without_test_leakage(tmp_path: Path) -> None:
    from edgeback.research.runner import run_walk_forward_research

    base_payload = yaml.safe_load((ROOT / "configs/example_backtest.yaml").read_text())
    base_payload["data"]["symbols"] = ["AAA"]
    base_payload["report"]["output_dir"] = str(tmp_path / "runs")
    base = tmp_path / "base_wf.yaml"
    base.write_text(yaml.safe_dump(base_payload), encoding="utf-8")
    research_payload = {
        "config_version": "1.0",
        "research": {
            "name": "tiny_walk_forward",
            "base_config": str(base),
            "random_seed": 9,
            "mode": "grid",
            "max_trials": 2,
            "split": {
                "method": "chronological_sessions",
                "train_pct": 60.0,
                "validation_pct": 20.0,
                "test_pct": 20.0,
                "embargo_sessions": 1,
                "final_test_immutable": True,
            },
            "selection": {
                "primary_metric": "validation_expectancy_usd_per_trade",
                "tie_breakers": ["validation_max_drawdown_pct"],
                "constraints": {
                    "minimum_validation_trades": 0,
                    "maximum_validation_drawdown_pct": 100.0,
                    "minimum_validation_profit_factor": 0.0,
                },
            },
            "parameter_grid": {"breakout_buffer_bps": [0.0, 5.0]},
            "walk_forward": {
                "enabled": True,
                "method": "rolling",
                "train_sessions": 6,
                "validation_sessions": 2,
                "test_sessions": 2,
                "step_sessions": 2,
            },
            "stress": {
                "cost_multipliers": [1.0, 2.0],
                "additional_entry_delay_bars": [0, 1],
                "remove_best_trade": True,
                "remove_best_session": True,
                "parameter_neighborhood": True,
                "bootstrap_sessions": 10,
            },
            "gates": {
                "minimum_oos_trades": 1,
                "maximum_single_trade_profit_contribution_pct": 100.0,
                "maximum_single_session_profit_contribution_pct": 100.0,
                "require_nonnegative_at_2x_cost": False,
                "require_parameter_plateau": False,
            },
        },
    }
    research_path = tmp_path / "wf.yaml"
    research_path.write_text(yaml.safe_dump(research_payload), encoding="utf-8")
    summary = run_walk_forward_research(research_path, fixture=True)
    assert summary["fold_count"] >= 1
    for fold in summary["folds"]:
        assert fold["selected"]["parameters"] in [
            {"breakout_buffer_bps": 0.0},
            {"breakout_buffer_bps": 5.0},
        ]
        assert Path(fold["run_path"]).exists()
    research_dir = tmp_path / "runs" / "research" / summary["research_id"]
    assert yaml.safe_load((research_dir / "RESEARCH_STATE.json").read_text())["state"] == "COMPLETED"
