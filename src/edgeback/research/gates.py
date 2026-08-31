"""Constrained research conclusion labels and promotion gates."""

from __future__ import annotations

from typing import Any

from edgeback.config.models import GateConfig

ALLOWED_CONCLUSIONS = (
    "ENGINE_VALIDATION_ONLY",
    "INSUFFICIENT_EVIDENCE",
    "IN_SAMPLE_ONLY",
    "OOS_FAILED",
    "OOS_PROMISING_NOT_ROBUST",
    "ROBUST_ON_TESTED_DATA",
)


def evaluate_research_gates(
    metrics: dict[str, Any],
    robustness: dict[str, Any],
    config: GateConfig,
    *,
    mechanical_tests_passed: bool = True,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, required: Any) -> None:
        gates.append({"name": name, "passed": bool(passed), "observed": observed, "required": required})

    expectancy = metrics.get("expectancy_usd_per_trade")
    trade_count = int(metrics.get("trade_count") or 0)
    add("mechanical_tests", mechanical_tests_passed, mechanical_tests_passed, True)
    add("positive_oos_expectancy", expectancy is not None and expectancy > 0, expectancy, "> 0")
    add("minimum_oos_trades", trade_count >= config.minimum_oos_trades, trade_count, config.minimum_oos_trades)
    trade_contribution = robustness.get("concentration", {}).get("single_trade_profit_contribution_pct")
    session_contribution = robustness.get("concentration", {}).get("single_session_profit_contribution_pct")
    add(
        "single_trade_concentration",
        trade_contribution is not None and trade_contribution <= config.maximum_single_trade_profit_contribution_pct,
        trade_contribution,
        f"<= {config.maximum_single_trade_profit_contribution_pct}%",
    )
    add(
        "single_session_concentration",
        session_contribution is not None and session_contribution <= config.maximum_single_session_profit_contribution_pct,
        session_contribution,
        f"<= {config.maximum_single_session_profit_contribution_pct}%",
    )
    two_x = next(
        (item for item in robustness.get("cost_stress", []) if abs(float(item.get("cost_multiplier", 0)) - 2.0) < 1e-9),
        None,
    )
    two_x_pass = not config.require_nonnegative_at_2x_cost or (two_x is not None and float(two_x.get("net_pnl_usd", -1)) >= 0)
    add("nonnegative_at_2x_cost", two_x_pass, two_x, "net P&L >= 0")
    plateau = bool(robustness.get("parameter_plateau", False))
    add("parameter_plateau", not config.require_parameter_plateau or plateau, plateau, True)

    positive = expectancy is not None and expectancy > 0
    if not mechanical_tests_passed:
        label = "OOS_FAILED"
    elif not positive:
        label = "OOS_FAILED"
    elif trade_count < config.minimum_oos_trades:
        label = "INSUFFICIENT_EVIDENCE"
    elif all(item["passed"] for item in gates):
        label = "ROBUST_ON_TESTED_DATA"
    else:
        label = "OOS_PROMISING_NOT_ROBUST"
    return {"label": label, "gates": gates, "all_passed": all(item["passed"] for item in gates)}
