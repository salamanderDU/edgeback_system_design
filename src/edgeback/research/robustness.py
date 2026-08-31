"""Post-run robustness diagnostics that never alter the original final test."""

from __future__ import annotations

from typing import Any

import pandas as pd


def concentration_diagnostics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "single_trade_profit_contribution_pct": None,
            "single_session_profit_contribution_pct": None,
            "remove_best_trade_net_pnl_usd": 0.0,
            "remove_best_session_net_pnl_usd": 0.0,
        }
    total = float(trades["net_pnl_usd"].sum())
    profitable = trades.loc[trades["net_pnl_usd"] > 0, "net_pnl_usd"].astype(float)
    best_trade = float(profitable.max()) if len(profitable) else 0.0
    session_pnl = trades.groupby("session_date", sort=True)["net_pnl_usd"].sum().astype(float)
    best_session = float(session_pnl.max()) if len(session_pnl) else 0.0
    denominator = total if total > 0 else None
    return {
        "single_trade_profit_contribution_pct": best_trade / denominator * 100.0 if denominator else None,
        "single_session_profit_contribution_pct": best_session / denominator * 100.0 if denominator else None,
        "remove_best_trade_net_pnl_usd": total - best_trade,
        "remove_best_session_net_pnl_usd": total - best_session,
    }


def restress_trade_costs(trades: pd.DataFrame, multiplier: float) -> dict[str, Any]:
    if trades.empty:
        return {"cost_multiplier": multiplier, "trade_count": 0, "net_pnl_usd": 0.0, "expectancy_usd_per_trade": None}
    net = trades["gross_pnl_usd"].astype(float) - trades["costs_usd"].astype(float) * multiplier
    return {
        "cost_multiplier": multiplier,
        "trade_count": int(len(net)),
        "net_pnl_usd": float(net.sum()),
        "expectancy_usd_per_trade": float(net.mean()),
    }
