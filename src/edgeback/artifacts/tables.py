"""Canonical result-table projections.

The engine owns event semantics.  This module only projects immutable domain events into stable,
column-oriented tables suitable for Parquet, CSV copies, metrics, and independent audit.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from edgeback.engine.state import BacktestResult
from edgeback.utils import canonical_json

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "intents": (
        "intent_id", "strategy_id", "strategy_version", "symbol", "side", "intent_type",
        "order_type", "signal_time_utc", "limit_price", "stop_trigger_price",
        "requested_quantity", "sizing_model", "entry_reference_price", "stop_loss_price",
        "take_profit_price", "expires_at_utc", "priority", "reason_code", "rationale",
        "protective_exit", "feature_snapshot_json",
    ),
    "decisions": (
        "intent_id", "accepted", "reason", "quantity", "estimated_risk_usd",
        "order_ids_json", "details_json",
    ),
    "orders": (
        "order_id", "intent_id", "parent_order_id", "strategy_id", "strategy_version",
        "symbol", "side", "order_type", "quantity", "status", "created_at_utc",
        "eligible_from_utc", "expires_at_utc", "limit_price", "stop_price",
        "bracket_stop_price", "bracket_target_price", "time_in_force", "priority",
        "creation_sequence", "reduce_only", "reason_code", "estimated_risk_usd", "tags_json",
    ),
    "order_events": (
        "event_id", "order_id", "timestamp_utc", "previous_status", "status", "reason_code",
        "details_json",
    ),
    "fills": (
        "fill_id", "order_id", "intent_id", "parent_order_id", "symbol", "side", "quantity",
        "timestamp_utc", "base_price", "spread_cost_usd", "slippage_cost_usd",
        "commission_usd", "total_cost_usd", "effective_price", "reason_code",
        "model_ids_json", "tags_json",
    ),
    "trades": (
        "trade_id", "symbol", "side", "quantity", "entry_fill_id", "exit_fill_id",
        "entry_order_id", "exit_order_id", "entry_time_utc", "exit_time_utc", "session_date",
        "entry_price", "exit_price", "gross_pnl_usd", "costs_usd", "net_pnl_usd",
        "holding_seconds", "exit_reason", "tags_json",
    ),
    "equity": (
        "timestamp_utc", "session_date", "cash_usd", "equity_usd", "gross_exposure_usd",
        "net_exposure_usd", "realized_pnl_usd", "unrealized_pnl_usd", "total_costs_usd",
    ),
    "warnings": (
        "warning_id", "timestamp_utc", "code", "message", "symbol", "context_json",
    ),
}

_INT_COLUMNS = {
    "intent_id", "requested_quantity", "priority", "quantity", "order_id", "parent_order_id",
    "creation_sequence", "event_id", "fill_id", "trade_id", "entry_fill_id", "exit_fill_id",
    "entry_order_id", "exit_order_id", "warning_id",
}
_FLOAT_COLUMNS = {
    "limit_price", "stop_trigger_price", "entry_reference_price", "stop_loss_price",
    "take_profit_price", "estimated_risk_usd", "bracket_stop_price", "bracket_target_price",
    "stop_price", "base_price", "spread_cost_usd", "slippage_cost_usd", "commission_usd",
    "total_cost_usd", "effective_price", "entry_price", "exit_price", "gross_pnl_usd",
    "costs_usd", "net_pnl_usd", "holding_seconds", "cash_usd", "equity_usd",
    "gross_exposure_usd", "net_exposure_usd", "realized_pnl_usd", "unrealized_pnl_usd",
}
_BOOL_COLUMNS = {"accepted", "reduce_only", "protective_exit"}
_TIMESTAMP_COLUMNS = {
    "signal_time_utc", "expires_at_utc", "created_at_utc", "eligible_from_utc",
    "timestamp_utc", "entry_time_utc", "exit_time_utc",
}


def _coerce_stable_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    coerced = frame.copy()
    for column in coerced.columns:
        if column in _TIMESTAMP_COLUMNS:
            coerced[column] = pd.to_datetime(coerced[column], utc=True)
        elif column in _INT_COLUMNS:
            coerced[column] = pd.to_numeric(coerced[column], errors="coerce").astype("Int64")
        elif column in _FLOAT_COLUMNS:
            coerced[column] = pd.to_numeric(coerced[column], errors="coerce").astype("Float64")
        elif column in _BOOL_COLUMNS:
            coerced[column] = coerced[column].astype("boolean")
        else:
            coerced[column] = coerced[column].astype("string")
    return coerced


def arrow_schema_for_table(name: str) -> object | None:
    if name not in TABLE_COLUMNS:
        raise KeyError(name)
    try:
        import pyarrow as pa
    except ImportError:
        return None
    fields = []
    for column in TABLE_COLUMNS[name]:
        if column in _TIMESTAMP_COLUMNS:
            data_type = pa.timestamp("us", tz="UTC")
        elif column in _INT_COLUMNS:
            data_type = pa.int64()
        elif column in _FLOAT_COLUMNS:
            data_type = pa.float64()
        elif column in _BOOL_COLUMNS:
            data_type = pa.bool_()
        else:
            data_type = pa.string()
        fields.append(pa.field(column, data_type, nullable=True))
    return pa.schema(fields)


def _enum(value: Any) -> Any:
    return getattr(value, "value", value)


def _json(value: Any) -> str:
    return canonical_json(value)


def _frame(name: str, records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    columns = list(TABLE_COLUMNS[name])
    frame = pd.DataFrame.from_records(list(records), columns=columns)
    return _coerce_stable_dtypes(frame)


def canonical_result_tables(result: BacktestResult) -> dict[str, pd.DataFrame]:
    intents = _frame(
        "intents",
        (
            {
                "intent_id": item.intent_id,
                "strategy_id": item.strategy_id,
                "strategy_version": item.strategy_version,
                "symbol": item.symbol,
                "side": _enum(item.side),
                "intent_type": _enum(item.intent_type),
                "order_type": _enum(item.order_type),
                "signal_time_utc": item.signal_time_utc,
                "limit_price": item.limit_price,
                "stop_trigger_price": item.stop_trigger_price,
                "requested_quantity": item.requested_quantity,
                "sizing_model": item.sizing_model,
                "entry_reference_price": item.entry_reference_price,
                "stop_loss_price": item.stop_loss_price,
                "take_profit_price": item.take_profit_price,
                "expires_at_utc": item.expires_at_utc,
                "priority": item.priority,
                "reason_code": item.reason_code,
                "rationale": item.rationale,
                "protective_exit": item.protective_exit,
                "feature_snapshot_json": _json(item.feature_snapshot),
            }
            for item in result.intents
        ),
    )
    decisions = _frame(
        "decisions",
        (
            {
                "intent_id": item.intent.intent_id,
                "accepted": item.accepted,
                "reason": _enum(item.reason),
                "quantity": item.quantity,
                "estimated_risk_usd": item.estimated_risk_usd,
                "order_ids_json": _json([order.order_id for order in item.orders]),
                "details_json": _json(item.details),
            }
            for item in result.risk_decisions
        ),
    )
    orders = _frame(
        "orders",
        (
            {
                "order_id": item.order_id,
                "intent_id": item.intent_id,
                "parent_order_id": item.parent_order_id,
                "strategy_id": item.strategy_id,
                "strategy_version": item.strategy_version,
                "symbol": item.symbol,
                "side": _enum(item.side),
                "order_type": _enum(item.order_type),
                "quantity": item.quantity,
                "status": _enum(item.status),
                "created_at_utc": item.created_at_utc,
                "eligible_from_utc": item.eligible_from_utc,
                "expires_at_utc": item.expires_at_utc,
                "limit_price": item.limit_price,
                "stop_price": item.stop_price,
                "bracket_stop_price": item.bracket_stop_price,
                "bracket_target_price": item.bracket_target_price,
                "time_in_force": _enum(item.time_in_force),
                "priority": item.priority,
                "creation_sequence": item.creation_sequence,
                "reduce_only": item.reduce_only,
                "reason_code": item.reason_code,
                "estimated_risk_usd": item.estimated_risk_usd,
                "tags_json": _json(item.tags),
            }
            for item in result.orders
        ),
    )
    order_events = _frame(
        "order_events",
        (
            {
                "event_id": item.event_id,
                "order_id": item.order_id,
                "timestamp_utc": item.timestamp_utc,
                "previous_status": _enum(item.previous_status),
                "status": _enum(item.status),
                "reason_code": item.reason_code,
                "details_json": _json(item.details),
            }
            for item in result.order_events
        ),
    )
    fills = _frame(
        "fills",
        (
            {
                "fill_id": item.fill_id,
                "order_id": item.order_id,
                "intent_id": item.intent_id,
                "parent_order_id": item.parent_order_id,
                "symbol": item.symbol,
                "side": _enum(item.side),
                "quantity": item.quantity,
                "timestamp_utc": item.timestamp_utc,
                "base_price": item.base_price,
                "spread_cost_usd": item.spread_cost_usd,
                "slippage_cost_usd": item.slippage_cost_usd,
                "commission_usd": item.commission_usd,
                "total_cost_usd": item.total_cost_usd,
                "effective_price": item.effective_price,
                "reason_code": item.reason_code,
                "model_ids_json": _json(item.model_ids),
                "tags_json": _json(item.tags),
            }
            for item in result.fills
        ),
    )
    trades = _frame(
        "trades",
        (
            {
                "trade_id": item.trade_id,
                "symbol": item.symbol,
                "side": _enum(item.side),
                "quantity": item.quantity,
                "entry_fill_id": item.entry_fill_id,
                "exit_fill_id": item.exit_fill_id,
                "entry_order_id": item.entry_order_id,
                "exit_order_id": item.exit_order_id,
                "entry_time_utc": item.entry_time_utc,
                "exit_time_utc": item.exit_time_utc,
                "session_date": item.session_date.isoformat(),
                "entry_price": item.entry_price,
                "exit_price": item.exit_price,
                "gross_pnl_usd": item.gross_pnl_usd,
                "costs_usd": item.costs_usd,
                "net_pnl_usd": item.net_pnl_usd,
                "holding_seconds": item.holding_seconds,
                "exit_reason": item.exit_reason,
                "tags_json": _json(item.tags),
            }
            for item in result.trades
        ),
    )
    equity = _frame(
        "equity",
        (
            {
                "timestamp_utc": item.timestamp_utc,
                "session_date": item.session_date,
                "cash_usd": item.cash_usd,
                "equity_usd": item.equity_usd,
                "gross_exposure_usd": item.gross_exposure_usd,
                "net_exposure_usd": item.net_exposure_usd,
                "realized_pnl_usd": item.realized_pnl_usd,
                "unrealized_pnl_usd": item.unrealized_pnl_usd,
                "total_costs_usd": item.total_costs_usd,
            }
            for item in result.equity
        ),
    )
    warnings = _frame(
        "warnings",
        (
            {
                "warning_id": item.warning_id,
                "timestamp_utc": item.timestamp_utc,
                "code": item.code,
                "message": item.message,
                "symbol": item.symbol,
                "context_json": _json(item.context),
            }
            for item in result.warnings
        ),
    )
    return {
        "intents": intents,
        "decisions": decisions,
        "orders": orders,
        "order_events": order_events,
        "fills": fills,
        "trades": trades,
        "equity": equity,
        "warnings": warnings,
    }


def validate_table_linkage(tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
    errors: list[str] = []
    intents = set(tables["intents"].get("intent_id", pd.Series(dtype="int64")).dropna().astype(int))
    orders = set(tables["orders"].get("order_id", pd.Series(dtype="int64")).dropna().astype(int))
    fills = set(tables["fills"].get("fill_id", pd.Series(dtype="int64")).dropna().astype(int))
    for value in tables["orders"].get("intent_id", pd.Series(dtype="float64")).dropna().astype(int):
        if value not in intents:
            errors.append(f"order references unknown intent {value}")
    for value in tables["fills"].get("order_id", pd.Series(dtype="int64")).dropna().astype(int):
        if value not in orders:
            errors.append(f"fill references unknown order {value}")
    for column in ("entry_fill_id", "exit_fill_id"):
        for value in tables["trades"].get(column, pd.Series(dtype="int64")).dropna().astype(int):
            if value not in fills:
                errors.append(f"trade references unknown fill {value}")
    for column in ("entry_order_id", "exit_order_id"):
        for value in tables["trades"].get(column, pd.Series(dtype="int64")).dropna().astype(int):
            if value not in orders:
                errors.append(f"trade references unknown order {value}")
    return tuple(errors)
