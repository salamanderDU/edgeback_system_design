"""Transparent cost-inclusive performance metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _ratio(numerator: float, denominator: float, reason_key: str, undefined: dict[str, str]) -> float | None:
    if denominator == 0:
        undefined[reason_key] = "denominator is zero"
        return None
    return numerator / denominator


def daily_returns_table(equity: pd.DataFrame, starting_equity: float) -> pd.DataFrame:
    columns = ["session_date", "ending_equity_usd", "daily_return"]
    if equity.empty:
        return pd.DataFrame(columns=columns)
    ordered = equity.sort_values(["timestamp_utc"], kind="stable")
    closes = ordered.groupby("session_date", sort=True, as_index=False).tail(1).copy()
    closes = closes[["session_date", "equity_usd"]].rename(columns={"equity_usd": "ending_equity_usd"})
    previous = closes["ending_equity_usd"].shift(1)
    if len(closes):
        previous.iloc[0] = starting_equity
    closes["daily_return"] = closes["ending_equity_usd"] / previous - 1.0
    return closes.reset_index(drop=True)[columns]


def _trade_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trade_count": 0,
            "net_pnl_usd": 0.0,
            "gross_pnl_usd": 0.0,
            "costs_usd": 0.0,
            "win_rate": None,
            "expectancy_usd_per_trade": None,
        }
    return {
        "trade_count": int(len(frame)),
        "net_pnl_usd": float(frame["net_pnl_usd"].sum()),
        "gross_pnl_usd": float(frame["gross_pnl_usd"].sum()),
        "costs_usd": float(frame["costs_usd"].sum()),
        "win_rate": float((frame["net_pnl_usd"] > 0).mean()),
        "expectancy_usd_per_trade": float(frame["net_pnl_usd"].mean()),
    }


def compute_metrics(
    tables: dict[str, pd.DataFrame],
    *,
    starting_equity_usd: float,
    data_completeness_pct: float | None = None,
    excluded_sessions: int = 0,
) -> dict[str, Any]:
    trades = tables["trades"].copy()
    fills = tables["fills"].copy()
    equity = tables["equity"].copy()
    warnings = tables["warnings"].copy()
    undefined: dict[str, str] = {}

    ending_equity = (
        float(equity.sort_values("timestamp_utc").iloc[-1]["equity_usd"])
        if not equity.empty
        else starting_equity_usd
    )
    net_pnl = ending_equity - starting_equity_usd
    gross_pnl = float(trades["gross_pnl_usd"].sum()) if not trades.empty else 0.0
    total_costs = float(fills["total_cost_usd"].sum()) if not fills.empty else 0.0
    net_return = net_pnl / starting_equity_usd

    max_drawdown_amount = 0.0
    max_drawdown_pct = 0.0
    average_exposure_pct = 0.0
    if not equity.empty:
        curve = equity.sort_values("timestamp_utc")["equity_usd"].astype(float)
        peaks = curve.cummax()
        drawdown = curve - peaks
        drawdown_pct = drawdown / peaks.replace(0.0, np.nan)
        max_drawdown_amount = float(abs(drawdown.min()))
        max_drawdown_pct = float(abs(drawdown_pct.min())) if drawdown_pct.notna().any() else 0.0
        exposure = equity["gross_exposure_usd"].astype(float) / equity["equity_usd"].replace(0.0, np.nan)
        average_exposure_pct = float(exposure.fillna(0.0).mean() * 100.0)

    daily = daily_returns_table(equity, starting_equity_usd)
    daily_values = daily["daily_return"].astype(float) if not daily.empty else pd.Series(dtype=float)
    daily_count = int(len(daily_values))
    sharpe: float | None
    sortino: float | None
    if daily_count < 2 or float(daily_values.std(ddof=1)) == 0.0:
        sharpe = None
        undefined["daily_sharpe"] = "fewer than two non-constant daily returns"
    else:
        sharpe = float(math.sqrt(252.0) * daily_values.mean() / daily_values.std(ddof=1))
    downside = daily_values[daily_values < 0]
    if len(downside) < 2 or float(downside.std(ddof=1)) == 0.0:
        sortino = None
        undefined["daily_sortino"] = "fewer than two non-constant downside observations"
    else:
        sortino = float(math.sqrt(252.0) * daily_values.mean() / downside.std(ddof=1))

    trade_count = int(len(trades))
    wins = trades.loc[trades["net_pnl_usd"] > 0, "net_pnl_usd"].astype(float) if trade_count else pd.Series(dtype=float)
    losses = trades.loc[trades["net_pnl_usd"] < 0, "net_pnl_usd"].astype(float) if trade_count else pd.Series(dtype=float)
    active_sessions = int(trades["session_date"].nunique()) if trade_count else 0
    win_rate = float(len(wins) / trade_count) if trade_count else None
    if trade_count == 0:
        undefined["win_rate"] = "no closed trades"
    average_win = float(wins.mean()) if len(wins) else None
    average_loss = float(losses.mean()) if len(losses) else None
    if average_win is None:
        undefined["average_win_usd"] = "no winning trades"
    if average_loss is None:
        undefined["average_loss_usd"] = "no losing trades"
    payoff = None
    if average_win is not None and average_loss is not None and average_loss != 0:
        payoff = average_win / abs(average_loss)
    else:
        undefined["payoff_ratio"] = "both winning and losing trades are required"
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    profit_factor = _ratio(gross_profit, gross_loss, "profit_factor", undefined)
    expectancy = float(trades["net_pnl_usd"].mean()) if trade_count else None
    if expectancy is None:
        undefined["expectancy_usd_per_trade"] = "no closed trades"

    cost_gross_ratio = _ratio(total_costs, gross_profit, "cost_to_gross_profit_ratio", undefined)
    notional_turnover = (
        float((fills["base_price"].astype(float) * fills["quantity"].astype(float)).abs().sum())
        if not fills.empty
        else 0.0
    )
    forced_exits = int((trades["exit_reason"] == "FORCED_SESSION_CLOSE").sum()) if trade_count else 0
    ambiguous_bars = int((warnings["code"] == "AMBIGUOUS_STOP_TARGET").sum()) if not warnings.empty else 0

    per_symbol = {
        str(key): _trade_summary(group)
        for key, group in trades.groupby("symbol", sort=True)
    } if trade_count else {}
    per_side = {
        str(key): _trade_summary(group)
        for key, group in trades.groupby("side", sort=True)
    } if trade_count else {}
    per_weekday: dict[str, Any] = {}
    per_entry_hour: dict[str, Any] = {}
    if trade_count:
        timestamps = pd.to_datetime(trades["entry_time_utc"], utc=True).dt.tz_convert("America/New_York")
        working = trades.assign(_weekday=timestamps.dt.day_name(), _hour=timestamps.dt.strftime("%H:00"))
        per_weekday = {str(key): _trade_summary(group) for key, group in working.groupby("_weekday", sort=True)}
        per_entry_hour = {str(key): _trade_summary(group) for key, group in working.groupby("_hour", sort=True)}

    return {
        "schema_version": "1.0",
        "units": {"currency": "USD", "returns": "decimal", "durations": "seconds"},
        "denominator_assumptions": {
            "return": "starting equity",
            "daily_sharpe_sortino": "close-to-close session returns, annualized by sqrt(252)",
            "turnover": "absolute filled base-price notional divided by starting equity",
        },
        "starting_equity_usd": starting_equity_usd,
        "ending_equity_usd": ending_equity,
        "gross_pnl_usd": gross_pnl,
        "net_pnl_usd": net_pnl,
        "net_return": net_return,
        "total_costs_usd": total_costs,
        "cost_to_gross_profit_ratio": cost_gross_ratio,
        "max_drawdown_usd": max_drawdown_amount,
        "max_drawdown_pct": max_drawdown_pct,
        "daily_sharpe": sharpe,
        "daily_sortino": sortino,
        "daily_observation_count": daily_count,
        "trade_count": trade_count,
        "active_sessions": active_sessions,
        "trades_per_active_session": trade_count / active_sessions if active_sessions else None,
        "win_rate": win_rate,
        "average_win_usd": average_win,
        "average_loss_usd": average_loss,
        "payoff_ratio": payoff,
        "expectancy_usd_per_trade": expectancy,
        "profit_factor": profit_factor,
        "average_holding_seconds": float(trades["holding_seconds"].mean()) if trade_count else None,
        "median_holding_seconds": float(trades["holding_seconds"].median()) if trade_count else None,
        "average_gross_exposure_pct": average_exposure_pct,
        "turnover_multiple": notional_turnover / starting_equity_usd,
        "forced_exit_count": forced_exits,
        "ambiguous_bar_count": ambiguous_bars,
        "data_completeness_pct": data_completeness_pct,
        "excluded_session_count": int(excluded_sessions),
        "per_symbol": per_symbol,
        "per_side": per_side,
        "per_weekday": per_weekday,
        "per_entry_hour": per_entry_hour,
        "undefined_reasons": undefined,
    }
