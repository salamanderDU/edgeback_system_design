"""Dependency-light self-contained HTML report renderer."""

from __future__ import annotations

import html
import json
import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from edgeback.config.models import ResolvedConfig


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fmt(value: Any, *, pct: bool = False, money: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return "—"
        if pct:
            return f"{float(value) * 100:.2f}%"
        if money:
            return f"${float(value):,.2f}"
        return f"{float(value):,.4f}"
    return _esc(value)


def _kv_table(items: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{_esc(key.replace('_', ' ').title())}</th><td>{_esc(value)}</td></tr>"
        for key, value in items.items()
    )
    return f"<table class='kv'>{rows}</table>"


def _line_svg(values: list[float], *, width: int = 900, height: int = 240) -> str:
    if not values:
        return "<p class='muted'>No observations.</p>"
    low, high = min(values), max(values)
    span = high - low or 1.0
    padding = 16
    usable_w = width - 2 * padding
    usable_h = height - 2 * padding
    points = []
    for index, value in enumerate(values):
        x = padding + usable_w * (index / max(1, len(values) - 1))
        y = padding + usable_h * (1.0 - (value - low) / span)
        points.append(f"{x:.2f},{y:.2f}")
    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Equity curve'>"
        f"<rect x='0' y='0' width='{width}' height='{height}' class='chart-bg'/>"
        f"<polyline points='{' '.join(points)}' class='chart-line'/></svg>"
    )


def _records_table(frame: pd.DataFrame, columns: list[str], limit: int = 50) -> str:
    if frame.empty:
        return "<p class='muted'>No records.</p>"
    selected = frame.loc[:, [column for column in columns if column in frame]].head(limit)
    header = "".join(f"<th>{_esc(column)}</th>" for column in selected.columns)
    rows: list[str] = []
    for record in selected.to_dict(orient="records"):
        cells = "".join(f"<td>{_esc(record.get(column, ''))}</td>" for column in selected.columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def render_html_report(
    *,
    metadata: dict[str, Any],
    config: ResolvedConfig,
    data_manifest: dict[str, Any],
    metrics: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    gate_results: dict[str, Any] | None = None,
) -> str:
    warnings = tables.get("warnings", pd.DataFrame())
    equity = tables.get("equity", pd.DataFrame())
    trades = tables.get("trades", pd.DataFrame())
    equity_values = equity["equity_usd"].astype(float).tolist() if not equity.empty else []
    summary = {
        "Conclusion": metadata.get("conclusion_label"),
        "Net P&L": _fmt(metrics.get("net_pnl_usd"), money=True),
        "Net return": _fmt(metrics.get("net_return"), pct=True),
        "Max drawdown": _fmt(metrics.get("max_drawdown_pct"), pct=True),
        "Trades": metrics.get("trade_count"),
        "Expectancy/trade": _fmt(metrics.get("expectancy_usd_per_trade"), money=True),
        "Profit factor": _fmt(metrics.get("profit_factor")),
        "Total costs": _fmt(metrics.get("total_costs_usd"), money=True),
    }
    execution = {
        "Fill timing": config.engine.market_fill_timing,
        "Same-bar policy": config.engine.same_bar_bracket_policy,
        "Full spread bps": config.execution.spread.full_spread_bps,
        "Slippage bps/side": config.execution.slippage.bps_per_side,
        "Commission model": config.execution.commission.model,
        "Force flat": config.engine.force_flat_at_session_end,
        "Allocation": config.engine.entry_allocation,
    }
    limitations = list(data_manifest.get("capability_snapshot", {}).get("limitations", []))
    licensing = data_manifest.get("licensing_warning")
    if licensing:
        limitations.append(str(licensing))
    limitation_html = "".join(f"<li>{_esc(item)}</li>" for item in limitations) or "<li>None recorded.</li>"
    gates = gate_results or {"label": metadata.get("conclusion_label"), "gates": []}
    warning_html = _records_table(warnings, ["timestamp_utc", "code", "symbol", "message"], 100)
    trade_html = _records_table(
        trades,
        ["trade_id", "symbol", "side", "entry_time_utc", "exit_time_utc", "net_pnl_usd", "exit_reason"],
        100,
    )
    breakdown = {
        "By symbol": metrics.get("per_symbol", {}),
        "By side": metrics.get("per_side", {}),
        "By weekday": metrics.get("per_weekday", {}),
        "By entry hour": metrics.get("per_entry_hour", {}),
    }
    return f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>EdgeBack Report {_esc(metadata.get('run_id'))}</title>
<style>
:root{{--ink:#17212b;--muted:#64748b;--line:#dbe2ea;--paper:#fff;--wash:#f4f7fa;--accent:#205493;--ok:#166534;--warn:#92400e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--wash);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:28px}} section{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:22px;margin:16px 0}}
h1{{margin:0 0 6px;font-size:30px}} h2{{font-size:19px;margin:0 0 14px}} .eyebrow{{text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-size:11px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}} .card{{border:1px solid var(--line);padding:14px;border-radius:8px}} .card b{{display:block;font-size:18px;margin-top:4px}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}} th{{background:#f8fafc}} .kv th{{width:32%}}
.table-wrap{{overflow:auto}} code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} pre{{white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:6px;overflow:auto}}
.muted{{color:var(--muted)}} .label{{display:inline-block;padding:4px 9px;border-radius:999px;background:#e8eef7;color:var(--accent);font-weight:700}}
.chart-bg{{fill:#fbfdff;stroke:#dbe2ea}} .chart-line{{fill:none;stroke:#205493;stroke-width:2.5}} svg{{width:100%;height:auto}}
</style></head><body><main>
<header><div class='eyebrow'>EdgeBack reproducible research report</div><h1>{_esc(config.project.name)}</h1><span class='label'>{_esc(metadata.get('conclusion_label'))}</span><p class='muted'>Run {_esc(metadata.get('run_id'))}</p></header>
<section><h2>1. Identity and reproducibility</h2>{_kv_table({
    'Run ID': metadata.get('run_id'), 'Logical identity': metadata.get('logical_identity_hash'),
    'Config hash': metadata.get('config_hash'), 'Data hash': metadata.get('data_manifest_hash'),
    'Strategy': f"{config.strategy.name} {config.strategy.expected_version or ''}",
    'Seed': config.project.random_seed, 'Status': metadata.get('status'),
})}</section>
<section><h2>2. Data, provider, and feed limitations</h2>{_kv_table({
    'Dataset': data_manifest.get('dataset_id'), 'Provider': data_manifest.get('provider'),
    'Feed': data_manifest.get('feed'), 'Interval seconds': data_manifest.get('interval_seconds'),
    'Adjustment': data_manifest.get('adjustment_mode'), 'Validation': data_manifest.get('validation', {}).get('status'),
})}<ul>{limitation_html}</ul></section>
<section><h2>3. Strategy and parameters</h2><pre>{_esc(json.dumps(config.strategy.model_dump(mode='json'), indent=2, sort_keys=True))}</pre></section>
<section><h2>4. Execution and risk assumptions</h2>{_kv_table(execution)}<pre>{_esc(json.dumps(config.risk.model_dump(mode='json'), indent=2, sort_keys=True))}</pre></section>
<section><h2>5. Summary and conclusion</h2><div class='grid'>{''.join(f"<div class='card'>{_esc(k)}<b>{_esc(v)}</b></div>" for k,v in summary.items())}</div></section>
<section><h2>6. Equity and drawdown</h2>{_line_svg(equity_values)}<p>Maximum drawdown: {_fmt(metrics.get('max_drawdown_usd'), money=True)} ({_fmt(metrics.get('max_drawdown_pct'), pct=True)})</p></section>
<section><h2>7. Daily/session returns</h2><p>Daily observations: {_esc(metrics.get('daily_observation_count'))}; Sharpe: {_fmt(metrics.get('daily_sharpe'))}; Sortino: {_fmt(metrics.get('daily_sortino'))}</p></section>
<section><h2>8. Trades and holding periods</h2>{trade_html}</section>
<section><h2>9. Breakdowns</h2><pre>{_esc(json.dumps(breakdown, indent=2, sort_keys=True))}</pre></section>
<section><h2>10. Cost waterfall and stress context</h2>{_kv_table({
    'Gross P&L': _fmt(metrics.get('gross_pnl_usd'), money=True), 'Total costs': _fmt(metrics.get('total_costs_usd'), money=True),
    'Net P&L': _fmt(metrics.get('net_pnl_usd'), money=True), 'Cost/gross-profit': _fmt(metrics.get('cost_to_gross_profit_ratio')),
    'Turnover multiple': _fmt(metrics.get('turnover_multiple')),
})}</section>
<section><h2>11. OOS, folds, and robustness</h2><pre>{_esc(json.dumps(gates, indent=2, sort_keys=True))}</pre></section>
<section><h2>12. Warnings, exclusions, and undefined metrics</h2>{warning_html}<pre>{_esc(json.dumps(metrics.get('undefined_reasons', {}), indent=2, sort_keys=True))}</pre></section>
<footer class='muted'>Research software only. Included strategies are hypotheses, not trading recommendations.</footer>
</main></body></html>"""
