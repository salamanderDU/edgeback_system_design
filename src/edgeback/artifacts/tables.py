"""Canonical run result tables (T500).

Turns the deterministic engine result objects
(:class:`~edgeback.engine.event_loop.EngineRunResult` and
:class:`~edgeback.engine.multi_symbol.MultiSymbolRunResult`) into stable Parquet
artifact tables with complete linkage and documented reason/cost fields
(``docs/07_CLI_CONFIG_AND_ARTIFACTS.md`` §8-11, ``docs/04_BACKTEST_ENGINE.md``
§6, §14).

Tables and their linkage
------------------------
- ``intents.parquet`` — every strategy :class:`~edgeback.domain.orders.OrderIntent`,
  including intents that were later rejected or suppressed (docs/04 §14). Rows are
  enumerated in engine emission order (``intent_seq``).
- ``decisions.parquet`` — every risk decision with its machine-readable reason
  code (docs/04 §8). ``intent_seq`` links back to the intents table;
  ``order_id`` links forward to the orders table when accepted.
- ``orders.parquet`` — every order known to the broker (final known state),
  including bracket children and engine-generated forced-close orders.
  ``order_id`` is the stable key used by fills/events/trades.
- ``order_events.parquet`` — every broker lifecycle event (accepted/filled/
  cancelled/rejected) with the order snapshot at that time (docs/04 §14
  "orders and status transitions"). ``event_seq`` is deterministic.
- ``fills.parquet`` — every fill with the T410 cost decomposition
  (commission/spread/slippage), total cost, and informational effective price
  (``docs/04_BACKTEST_ENGINE.md`` §6). ``order_id`` links to the orders table.
- ``trades.parquet`` — closed round trips with entry/exit fill and order
  linkage (docs/04 §14). Realized P&L uses **base execution prices** exactly
  like the ledger and ``edgeback.portfolio.accounting``; costs are attributed
  pro-rata from the entry and exit fills. Position flips (a close that crosses
  through flat) produce one trade per closed lot then open a new lot.
  Positions still open at run end produce no trade row.
- ``equity.parquet`` — per-bar-end portfolio snapshots (cash, equity, gross/net
  exposure) in deterministic engine order (docs/04 §14).
- ``warnings.parquet`` — run warnings (warmup suppression, ambiguous bars,
  forced session closes, etc.).

All writers consume either result type unchanged; both engine result classes
expose the same tuple fields. ``run_status`` (``COMPLETED``/``FAILED``) is
carried on every table so a partially recorded failure still yields readable,
truthful artifacts (docs/02 §9, NFR-004).

Writers are deterministic and offline. The run-level atomic directory writer,
checksums, and metadata JSON are added by T520 on top of these builders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from edgeback.domain.fills import Fill
from edgeback.domain.orders import Order, OrderEvent, OrderIntent
from edgeback.engine.event_loop import EquityPoint
from edgeback.portfolio.accounting import effective_price, round_money
from edgeback.portfolio.ledger import ReconciliationReport
from edgeback.risk.manager import RiskDecision

__all__ = [
    "ClosedTrade",
    "RunResultTables",
    "build_decisions_frame",
    "build_equity_frame",
    "build_fills_frame",
    "build_intents_frame",
    "build_order_events_frame",
    "build_orders_frame",
    "build_trades_frame",
    "build_warnings_frame",
    "trades_from_fills",
    "write_run_tables",
]

# ---------------------------------------------------------------------------
# Stable Arrow schemas (T500 "Parquet schemas stable")
# ---------------------------------------------------------------------------

UTC_T = pa.timestamp("us", tz="UTC")


class RunResultTables(Protocol):
    """Structural type shared by both engine result dataclasses."""

    status: str
    strategy_id: str
    strategy_version: str
    intents: tuple[OrderIntent, ...]
    decisions: tuple[RiskDecision, ...]
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    broker_events: tuple[OrderEvent, ...]
    warnings: tuple[str, ...]
    equity_curve: tuple[EquityPoint, ...]
    reconciliation: ReconciliationReport | None


_INTENTS_SCHEMA = pa.schema(
    [
        pa.field("intent_seq", pa.int64()),
        pa.field("symbol", pa.string()),
        pa.field("direction", pa.string()),
        pa.field("intent_type", pa.string()),
        pa.field("limit_price", pa.float64()),
        pa.field("stop_price", pa.float64()),
        pa.field("take_profit_price", pa.float64()),
        pa.field("requested_shares", pa.int64()),
        pa.field("tag", pa.string()),
        pa.field("protective_exit", pa.bool_()),
        pa.field("priority", pa.int64()),
        pa.field("strategy_id", pa.string()),
        pa.field("strategy_version", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_DECISIONS_SCHEMA = pa.schema(
    [
        pa.field("decision_seq", pa.int64()),
        pa.field("intent_seq", pa.int64()),
        pa.field("symbol", pa.string()),
        pa.field("direction", pa.string()),
        pa.field("intent_type", pa.string()),
        pa.field("accepted", pa.bool_()),
        pa.field("reason", pa.string()),
        pa.field("message", pa.string()),
        pa.field("sized_shares", pa.int64()),
        pa.field("order_id", pa.string()),
        pa.field("strategy_id", pa.string()),
        pa.field("strategy_version", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_ORDERS_SCHEMA = pa.schema(
    [
        pa.field("order_id", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("direction", pa.string()),
        pa.field("order_type", pa.string()),
        pa.field("shares", pa.int64()),
        pa.field("limit_price", pa.float64()),
        pa.field("stop_price", pa.float64()),
        pa.field("take_profit_price", pa.float64()),
        pa.field("stop_loss_price", pa.float64()),
        pa.field("status", pa.string()),
        pa.field("reason", pa.string()),
        pa.field("eligible_from_utc", UTC_T),
        pa.field("expires_at_utc", UTC_T),
        pa.field("parent_order_id", pa.string()),
        pa.field("priority", pa.int64()),
        pa.field("creation_sequence", pa.int64()),
        pa.field("strategy_id", pa.string()),
        pa.field("strategy_version", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_ORDER_EVENTS_SCHEMA = pa.schema(
    [
        pa.field("event_seq", pa.int64()),
        pa.field("event_type", pa.string()),
        pa.field("timestamp_utc", UTC_T),
        pa.field("order_id", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("status", pa.string()),
        pa.field("reason", pa.string()),
        pa.field("parent_order_id", pa.string()),
        pa.field("creation_sequence", pa.int64()),
        pa.field("strategy_id", pa.string()),
        pa.field("strategy_version", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_FILLS_SCHEMA = pa.schema(
    [
        pa.field("fill_id", pa.string()),
        pa.field("order_id", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("timestamp_utc", UTC_T),
        pa.field("direction", pa.string()),
        pa.field("action", pa.string()),
        pa.field("shares", pa.int64()),
        pa.field("fill_price", pa.float64()),
        pa.field("commission_usd", pa.float64()),
        pa.field("slippage_usd", pa.float64()),
        pa.field("spread_usd", pa.float64()),
        pa.field("total_cost_usd", pa.float64()),
        pa.field("effective_price", pa.float64()),
        pa.field("reason", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_TRADES_SCHEMA = pa.schema(
    [
        pa.field("trade_seq", pa.int64()),
        pa.field("symbol", pa.string()),
        pa.field("side", pa.string()),
        pa.field("entry_order_id", pa.string()),
        pa.field("entry_fill_id", pa.string()),
        pa.field("entry_timestamp_utc", UTC_T),
        pa.field("entry_price", pa.float64()),
        pa.field("exit_order_id", pa.string()),
        pa.field("exit_fill_id", pa.string()),
        pa.field("exit_timestamp_utc", UTC_T),
        pa.field("exit_price", pa.float64()),
        pa.field("shares", pa.int64()),
        pa.field("realized_pnl", pa.float64()),
        pa.field("entry_cost_usd", pa.float64()),
        pa.field("exit_cost_usd", pa.float64()),
        pa.field("total_cost_usd", pa.float64()),
        pa.field("net_pnl", pa.float64()),
        pa.field("exit_reason", pa.string()),
        pa.field("holding_seconds", pa.float64()),
        pa.field("run_status", pa.string()),
    ]
)

_WARNINGS_SCHEMA = pa.schema(
    [
        pa.field("warning_seq", pa.int64()),
        pa.field("message", pa.string()),
        pa.field("run_status", pa.string()),
    ]
)

_EQUITY_SCHEMA = pa.schema(
    [
        pa.field("bar_end_utc", UTC_T),
        pa.field("cash", pa.float64()),
        pa.field("equity", pa.float64()),
        pa.field("gross_exposure", pa.float64()),
        pa.field("net_exposure", pa.float64()),
        pa.field("run_status", pa.string()),
    ]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(values: Sequence[Any]) -> pd.Series:
    """Timezone-aware UTC pandas series; ``None`` becomes ``NaT``."""
    parsed: list[Any] = []
    for value in values:
        if value is None:
            parsed.append(pd.NaT)
        else:
            parsed.append(value.astimezone(UTC))
    return pd.Series(parsed, dtype="datetime64[us, UTC]")


def _col(values: Sequence[Any], dtype: str) -> pd.Series:
    return pd.Series(values, dtype=dtype)


def _write_frame(frame: pd.DataFrame, schema: pa.Schema, path: Path) -> None:
    """Write a pandas frame to Parquet with the exact stable Arrow schema."""
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    pq.write_table(table, path)


def _intent_index(result: RunResultTables) -> dict[OrderIntent, int]:
    """Deterministic emission-order index for intents (docs/04 §14)."""
    return {intent: seq for seq, intent in enumerate(result.intents)}


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def build_intents_frame(result: RunResultTables) -> pd.DataFrame:
    """All strategy intents in engine emission order (including rejected)."""
    rows = []
    for seq, intent in enumerate(result.intents):
        rows.append(
            {
                "intent_seq": seq,
                "symbol": intent.symbol,
                "direction": intent.direction,
                "intent_type": intent.intent_type,
                "limit_price": intent.limit_price,
                "stop_price": intent.stop_price,
                "take_profit_price": intent.take_profit_price,
                "requested_shares": intent.requested_shares,
                "tag": intent.tag,
                "protective_exit": intent.protective_exit,
                "priority": intent.priority,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "intent_seq": _col([r["intent_seq"] for r in rows], "int64"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "direction": _col([r["direction"] for r in rows], "string"),
            "intent_type": _col([r["intent_type"] for r in rows], "string"),
            "limit_price": _col([r["limit_price"] for r in rows], "float64"),
            "stop_price": _col([r["stop_price"] for r in rows], "float64"),
            "take_profit_price": _col([r["take_profit_price"] for r in rows], "float64"),
            "requested_shares": _col([r["requested_shares"] for r in rows], "Int64"),
            "tag": _col([r["tag"] for r in rows], "string"),
            "protective_exit": _col([r["protective_exit"] for r in rows], "bool"),
            "priority": _col([r["priority"] for r in rows], "int64"),
            "strategy_id": _col([r["strategy_id"] for r in rows], "string"),
            "strategy_version": _col([r["strategy_version"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_decisions_frame(result: RunResultTables) -> pd.DataFrame:
    """Every risk decision with reason codes and intent/order linkage."""
    intent_index = _intent_index(result)
    rows = []
    for seq, decision in enumerate(result.decisions):
        rows.append(
            {
                "decision_seq": seq,
                "intent_seq": intent_index.get(decision.intent, -1),
                "symbol": decision.intent.symbol,
                "direction": decision.intent.direction,
                "intent_type": decision.intent.intent_type,
                "accepted": decision.accepted,
                "reason": decision.reason.value,
                "message": decision.message,
                "sized_shares": decision.sized_shares,
                "order_id": decision.order.id if decision.order is not None else None,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "decision_seq": _col([r["decision_seq"] for r in rows], "int64"),
            "intent_seq": _col([r["intent_seq"] for r in rows], "int64"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "direction": _col([r["direction"] for r in rows], "string"),
            "intent_type": _col([r["intent_type"] for r in rows], "string"),
            "accepted": _col([r["accepted"] for r in rows], "bool"),
            "reason": _col([r["reason"] for r in rows], "string"),
            "message": _col([r["message"] for r in rows], "string"),
            "sized_shares": _col([r["sized_shares"] for r in rows], "Int64"),
            "order_id": _col([r["order_id"] for r in rows], "string"),
            "strategy_id": _col([r["strategy_id"] for r in rows], "string"),
            "strategy_version": _col([r["strategy_version"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_orders_frame(result: RunResultTables) -> pd.DataFrame:
    """Final known state of every order known to the broker."""
    rows = []
    for order in result.orders:
        rows.append(
            {
                "order_id": order.id,
                "symbol": order.symbol,
                "direction": order.direction,
                "order_type": order.order_type,
                "shares": order.shares,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "take_profit_price": order.take_profit_price,
                "stop_loss_price": order.stop_loss_price,
                "status": order.status,
                "reason": order.reason,
                "eligible_from_utc": order.eligible_from_utc,
                "expires_at_utc": order.expires_at_utc,
                "parent_order_id": order.parent_order_id,
                "priority": order.priority,
                "creation_sequence": order.creation_sequence,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "order_id": _col([r["order_id"] for r in rows], "string"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "direction": _col([r["direction"] for r in rows], "string"),
            "order_type": _col([r["order_type"] for r in rows], "string"),
            "shares": _col([r["shares"] for r in rows], "int64"),
            "limit_price": _col([r["limit_price"] for r in rows], "float64"),
            "stop_price": _col([r["stop_price"] for r in rows], "float64"),
            "take_profit_price": _col([r["take_profit_price"] for r in rows], "float64"),
            "stop_loss_price": _col([r["stop_loss_price"] for r in rows], "float64"),
            "status": _col([r["status"] for r in rows], "string"),
            "reason": _col([r["reason"] for r in rows], "string"),
            "eligible_from_utc": _ts([r["eligible_from_utc"] for r in rows]),
            "expires_at_utc": _ts([r["expires_at_utc"] for r in rows]),
            "parent_order_id": _col([r["parent_order_id"] for r in rows], "string"),
            "priority": _col([r["priority"] for r in rows], "int64"),
            "creation_sequence": _col([r["creation_sequence"] for r in rows], "int64"),
            "strategy_id": _col([r["strategy_id"] for r in rows], "string"),
            "strategy_version": _col([r["strategy_version"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_order_events_frame(result: RunResultTables) -> pd.DataFrame:
    """Broker lifecycle events (status transitions) in creation order."""
    rows = []
    for seq, event in enumerate(result.broker_events):
        rows.append(
            {
                "event_seq": seq,
                "event_type": event.event_type,
                "timestamp_utc": datetime.fromisoformat(event.timestamp_utc)
                if event.timestamp_utc
                else None,
                "order_id": event.order.id,
                "symbol": event.order.symbol,
                "status": event.order.status,
                "reason": event.reason or event.order.reason,
                "parent_order_id": event.order.parent_order_id,
                "creation_sequence": event.order.creation_sequence,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "event_seq": _col([r["event_seq"] for r in rows], "int64"),
            "event_type": _col([r["event_type"] for r in rows], "string"),
            "timestamp_utc": _ts([r["timestamp_utc"] for r in rows]),
            "order_id": _col([r["order_id"] for r in rows], "string"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "status": _col([r["status"] for r in rows], "string"),
            "reason": _col([r["reason"] for r in rows], "string"),
            "parent_order_id": _col([r["parent_order_id"] for r in rows], "string"),
            "creation_sequence": _col([r["creation_sequence"] for r in rows], "int64"),
            "strategy_id": _col([r["strategy_id"] for r in rows], "string"),
            "strategy_version": _col([r["strategy_version"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_fills_frame(result: RunResultTables) -> pd.DataFrame:
    """Every fill with the T410 cost decomposition and effective price."""
    rows = []
    for fill in result.fills:
        total_cost = round_money(fill.commission_usd + fill.slippage_usd + fill.spread_usd)
        rows.append(
            {
                "fill_id": fill.id,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "timestamp_utc": fill.timestamp_utc,
                "direction": fill.direction,
                "action": fill.action,
                "shares": fill.shares,
                "fill_price": fill.fill_price,
                "commission_usd": fill.commission_usd,
                "slippage_usd": fill.slippage_usd,
                "spread_usd": fill.spread_usd,
                "total_cost_usd": total_cost,
                "effective_price": effective_price(fill),
                "reason": fill.reason,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "fill_id": _col([r["fill_id"] for r in rows], "string"),
            "order_id": _col([r["order_id"] for r in rows], "string"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "timestamp_utc": _ts([r["timestamp_utc"] for r in rows]),
            "direction": _col([r["direction"] for r in rows], "string"),
            "action": _col([r["action"] for r in rows], "string"),
            "shares": _col([r["shares"] for r in rows], "int64"),
            "fill_price": _col([r["fill_price"] for r in rows], "float64"),
            "commission_usd": _col([r["commission_usd"] for r in rows], "float64"),
            "slippage_usd": _col([r["slippage_usd"] for r in rows], "float64"),
            "spread_usd": _col([r["spread_usd"] for r in rows], "float64"),
            "total_cost_usd": _col([r["total_cost_usd"] for r in rows], "float64"),
            "effective_price": _col([r["effective_price"] for r in rows], "float64"),
            "reason": _col([r["reason"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_equity_frame(result: RunResultTables) -> pd.DataFrame:
    """Per-bar-end portfolio snapshots in deterministic engine order."""
    rows = []
    for point in result.equity_curve:
        rows.append(
            {
                "bar_end_utc": point.timestamp_utc,
                "cash": point.cash,
                "equity": point.equity,
                "gross_exposure": point.gross_exposure,
                "net_exposure": point.net_exposure,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "bar_end_utc": _ts([r["bar_end_utc"] for r in rows]),
            "cash": _col([r["cash"] for r in rows], "float64"),
            "equity": _col([r["equity"] for r in rows], "float64"),
            "gross_exposure": _col([r["gross_exposure"] for r in rows], "float64"),
            "net_exposure": _col([r["net_exposure"] for r in rows], "float64"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


def build_warnings_frame(result: RunResultTables) -> pd.DataFrame:
    """Run warnings in recorded order."""
    rows = [
        {"warning_seq": seq, "message": message, "run_status": result.status}
        for seq, message in enumerate(result.warnings)
    ]
    return pd.DataFrame(
        {
            "warning_seq": _col([r["warning_seq"] for r in rows], "int64"),
            "message": _col([r["message"] for r in rows], "string"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


# ---------------------------------------------------------------------------
# Closed-trade construction (FIFO lots, base-price P&L, pro-rata costs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosedTrade:
    """A fully closed round trip with entry/exit linkage (docs/04 §14)."""

    symbol: str
    side: str
    entry_order_id: str
    entry_fill_id: str
    entry_timestamp_utc: datetime
    entry_price: float
    exit_order_id: str
    exit_fill_id: str
    exit_timestamp_utc: datetime
    exit_price: float
    shares: int
    realized_pnl: float
    entry_cost_usd: float
    exit_cost_usd: float
    exit_reason: str
    holding_seconds: float

    @property
    def total_cost_usd(self) -> float:
        return round_money(self.entry_cost_usd + self.exit_cost_usd)

    @property
    def net_pnl(self) -> float:
        return round_money(self.realized_pnl - self.total_cost_usd)


class _MutableLot:
    """FIFO open lot; costs pro-rated from the original entry fill."""

    def __init__(
        self,
        symbol: str,
        side: str,
        shares: int,
        entry_order_id: str,
        entry_fill_id: str,
        entry_timestamp_utc: datetime,
        entry_price: float,
        entry_fill_cost_usd: float,
        entry_fill_shares: int,
    ) -> None:
        self.symbol = symbol
        self.side = side
        self.shares = shares
        self.entry_order_id = entry_order_id
        self.entry_fill_id = entry_fill_id
        self.entry_timestamp_utc = entry_timestamp_utc
        self.entry_price = entry_price
        self.entry_fill_cost_usd = entry_fill_cost_usd
        self.entry_fill_shares = entry_fill_shares

    def entry_cost_for(self, closed: int) -> float:
        return round_money(self.entry_fill_cost_usd * closed / self.entry_fill_shares)


def _exit_reason(order: Order | None, fill: Fill) -> str:
    """Human-meaningful exit label from the exit order/fill.

    Protective children are identified structurally *before* ``order.reason``:
    once a child fills, the broker overwrites the child's ``reason`` with the
    fill reason (``market_fill``), so relying on ``reason`` alone would lose
    the stop-loss/take-profit role of the exit (docs/04 §14).
    """
    if order is None:
        return fill.reason or "MARKET"
    if order.parent_order_id is not None:
        if order.order_type == "stop":
            return "STOP_LOSS"
        if order.order_type == "limit":
            return "TAKE_PROFIT"
    if order.reason:
        return order.reason
    return fill.reason or "MARKET"


def trades_from_fills(fills: Sequence[Fill], orders: Sequence[Order]) -> list[ClosedTrade]:
    """Build closed-trade round trips from fills/orders (FIFO lot matching).

    The realized P&L uses base execution prices consistent with
    ``edgeback.portfolio.accounting``: a long closes at
    ``(exit_base - entry_base) * shares`` and a short at
    ``(short_entry_base - cover_base) * covered``. Entry/exit costs are
    attributed pro-rata from the originating fills, so when a run ends flat the
    sum of ``total_cost_usd`` equals the sum of all fill costs (docs/04 §6).
    A flip (a fill that crosses through flat) emits one closed trade per lot
    consumed, then opens a fresh lot for the remainder.
    """
    order_by_id = {order.id: order for order in orders}
    lots: dict[str, list[_MutableLot]] = {}
    trades: list[ClosedTrade] = []

    for fill in fills:
        fill_cost = round_money(fill.commission_usd + fill.slippage_usd + fill.spread_usd)
        symbol_lots = lots.setdefault(fill.symbol, [])
        remaining = fill.shares

        if fill.action == "sell":
            # Close open longs first (FIFO), then open a short for remainder.
            while remaining > 0 and symbol_lots and symbol_lots[0].side == "long":
                lot = symbol_lots[0]
                closed = min(remaining, lot.shares)
                realized = round_money(closed * (fill.fill_price - lot.entry_price))
                assert lot.entry_fill_shares > 0
                entry_cost = lot.entry_cost_for(closed)
                exit_cost = round_money(fill_cost * closed / fill.shares)
                trades.append(
                    ClosedTrade(
                        symbol=fill.symbol,
                        side="long",
                        entry_order_id=lot.entry_order_id,
                        entry_fill_id=lot.entry_fill_id,
                        entry_timestamp_utc=lot.entry_timestamp_utc,
                        entry_price=lot.entry_price,
                        exit_order_id=fill.order_id,
                        exit_fill_id=fill.id,
                        exit_timestamp_utc=fill.timestamp_utc,
                        exit_price=fill.fill_price,
                        shares=closed,
                        realized_pnl=realized,
                        entry_cost_usd=entry_cost,
                        exit_cost_usd=exit_cost,
                        exit_reason=_exit_reason(order_by_id.get(fill.order_id), fill),
                        holding_seconds=(
                            fill.timestamp_utc - lot.entry_timestamp_utc
                        ).total_seconds(),
                    )
                )
                remaining -= closed
                lot.shares -= closed
                if lot.shares == 0:
                    symbol_lots.pop(0)
            if remaining > 0:
                symbol_lots.append(
                    _MutableLot(
                        symbol=fill.symbol,
                        side="short",
                        shares=remaining,
                        entry_order_id=fill.order_id,
                        entry_fill_id=fill.id,
                        entry_timestamp_utc=fill.timestamp_utc,
                        entry_price=fill.fill_price,
                        entry_fill_cost_usd=fill_cost,
                        entry_fill_shares=fill.shares,
                    )
                )
        else:  # buy
            # Cover open shorts first (FIFO), then open a long for remainder.
            while remaining > 0 and symbol_lots and symbol_lots[0].side == "short":
                lot = symbol_lots[0]
                closed = min(remaining, lot.shares)
                realized = round_money(closed * (lot.entry_price - fill.fill_price))
                assert lot.entry_fill_shares > 0
                entry_cost = lot.entry_cost_for(closed)
                exit_cost = round_money(fill_cost * closed / fill.shares)
                trades.append(
                    ClosedTrade(
                        symbol=fill.symbol,
                        side="short",
                        entry_order_id=lot.entry_order_id,
                        entry_fill_id=lot.entry_fill_id,
                        entry_timestamp_utc=lot.entry_timestamp_utc,
                        entry_price=lot.entry_price,
                        exit_order_id=fill.order_id,
                        exit_fill_id=fill.id,
                        exit_timestamp_utc=fill.timestamp_utc,
                        exit_price=fill.fill_price,
                        shares=closed,
                        realized_pnl=realized,
                        entry_cost_usd=entry_cost,
                        exit_cost_usd=exit_cost,
                        exit_reason=_exit_reason(order_by_id.get(fill.order_id), fill),
                        holding_seconds=(
                            fill.timestamp_utc - lot.entry_timestamp_utc
                        ).total_seconds(),
                    )
                )
                remaining -= closed
                lot.shares -= closed
                if lot.shares == 0:
                    symbol_lots.pop(0)
            if remaining > 0:
                symbol_lots.append(
                    _MutableLot(
                        symbol=fill.symbol,
                        side="long",
                        shares=remaining,
                        entry_order_id=fill.order_id,
                        entry_fill_id=fill.id,
                        entry_timestamp_utc=fill.timestamp_utc,
                        entry_price=fill.fill_price,
                        entry_fill_cost_usd=fill_cost,
                        entry_fill_shares=fill.shares,
                    )
                )

    return trades


def build_trades_frame(result: RunResultTables) -> pd.DataFrame:
    """Closed trades with entry/exit linkage (docs/04 §14)."""
    trades = trades_from_fills(result.fills, result.orders)
    rows = []
    for seq, trade in enumerate(trades):
        rows.append(
            {
                "trade_seq": seq,
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_order_id": trade.entry_order_id,
                "entry_fill_id": trade.entry_fill_id,
                "entry_timestamp_utc": trade.entry_timestamp_utc,
                "entry_price": trade.entry_price,
                "exit_order_id": trade.exit_order_id,
                "exit_fill_id": trade.exit_fill_id,
                "exit_timestamp_utc": trade.exit_timestamp_utc,
                "exit_price": trade.exit_price,
                "shares": trade.shares,
                "realized_pnl": trade.realized_pnl,
                "entry_cost_usd": trade.entry_cost_usd,
                "exit_cost_usd": trade.exit_cost_usd,
                "total_cost_usd": trade.total_cost_usd,
                "net_pnl": trade.net_pnl,
                "exit_reason": trade.exit_reason,
                "holding_seconds": trade.holding_seconds,
                "run_status": result.status,
            }
        )
    return pd.DataFrame(
        {
            "trade_seq": _col([r["trade_seq"] for r in rows], "int64"),
            "symbol": _col([r["symbol"] for r in rows], "string"),
            "side": _col([r["side"] for r in rows], "string"),
            "entry_order_id": _col([r["entry_order_id"] for r in rows], "string"),
            "entry_fill_id": _col([r["entry_fill_id"] for r in rows], "string"),
            "entry_timestamp_utc": _ts([r["entry_timestamp_utc"] for r in rows]),
            "entry_price": _col([r["entry_price"] for r in rows], "float64"),
            "exit_order_id": _col([r["exit_order_id"] for r in rows], "string"),
            "exit_fill_id": _col([r["exit_fill_id"] for r in rows], "string"),
            "exit_timestamp_utc": _ts([r["exit_timestamp_utc"] for r in rows]),
            "exit_price": _col([r["exit_price"] for r in rows], "float64"),
            "shares": _col([r["shares"] for r in rows], "int64"),
            "realized_pnl": _col([r["realized_pnl"] for r in rows], "float64"),
            "entry_cost_usd": _col([r["entry_cost_usd"] for r in rows], "float64"),
            "exit_cost_usd": _col([r["exit_cost_usd"] for r in rows], "float64"),
            "total_cost_usd": _col([r["total_cost_usd"] for r in rows], "float64"),
            "net_pnl": _col([r["net_pnl"] for r in rows], "float64"),
            "exit_reason": _col([r["exit_reason"] for r in rows], "string"),
            "holding_seconds": _col([r["holding_seconds"] for r in rows], "float64"),
            "run_status": _col([r["run_status"] for r in rows], "string"),
        }
    )


# ---------------------------------------------------------------------------
# Combined writer (T520 consumes this; atomicity/metadata added there)
# ---------------------------------------------------------------------------


def write_run_tables(result: RunResultTables, output_dir: Path) -> list[Path]:
    """Write all canonical result tables into ``output_dir`` as Parquet.

    Returns the sorted list of written file paths. The directory is created if
    needed. Table writers require content they can produce from the engine
    result; the run-level atomic directory/checksum/metadata handling belongs
    to T520.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables: dict[str, tuple[pd.DataFrame, pa.Schema]] = {
        "intents.parquet": (build_intents_frame(result), _INTENTS_SCHEMA),
        "decisions.parquet": (build_decisions_frame(result), _DECISIONS_SCHEMA),
        "orders.parquet": (build_orders_frame(result), _ORDERS_SCHEMA),
        "order_events.parquet": (
            build_order_events_frame(result),
            _ORDER_EVENTS_SCHEMA,
        ),
        "fills.parquet": (build_fills_frame(result), _FILLS_SCHEMA),
        "trades.parquet": (build_trades_frame(result), _TRADES_SCHEMA),
        "equity.parquet": (build_equity_frame(result), _EQUITY_SCHEMA),
        "warnings.parquet": (build_warnings_frame(result), _WARNINGS_SCHEMA),
    }
    written: list[Path] = []
    for name in sorted(tables):
        frame, schema = tables[name]
        path = output_dir / name
        _write_frame(frame, schema, path)
        written.append(path)
    return written
