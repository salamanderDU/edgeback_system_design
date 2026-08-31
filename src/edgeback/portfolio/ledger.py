from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from edgeback.domain import (
    Fill,
    IdAllocator,
    PortfolioSnapshot,
    Position,
    PositionSide,
    Trade,
)
from edgeback.errors import SimulationError

_ET = ZoneInfo("America/New_York")


@dataclass(slots=True)
class _Lot:
    signed_quantity: int
    price: float
    fill_id: int
    order_id: int
    time_utc: datetime
    entry_cost_per_share: float


class PortfolioLedger:
    def __init__(self, initial_cash_usd: float, ids: IdAllocator, *, max_leverage: float = 1.0) -> None:
        if initial_cash_usd <= 0:
            raise ValueError("initial cash must be positive")
        self.initial_cash_usd = float(initial_cash_usd)
        self.cash_usd = float(initial_cash_usd)
        self.max_leverage = float(max_leverage)
        self._ids = ids
        self._lots: dict[str, deque[_Lot]] = {}
        self._marks: dict[str, float] = {}
        self._realized_gross_usd = 0.0
        self._realized_by_symbol: dict[str, float] = {}
        self._total_costs_usd = 0.0
        self._last_timestamp: datetime | None = None
        self._last_fill_id = 0
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []

    def _validated_time(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            raise SimulationError("Ledger timestamp must be timezone-aware")
        normalized = timestamp.astimezone(UTC)
        if self._last_timestamp is not None and normalized < self._last_timestamp:
            raise SimulationError("Ledger events must be non-decreasing in time")
        return normalized

    def _projected_leverage(self, fill: Fill) -> tuple[float, float]:
        quantities = {position.symbol: position.quantity for position in self.positions()}
        marks = {position.symbol: position.last_price for position in self.positions()}
        quantities[fill.symbol] = quantities.get(fill.symbol, 0) + fill.side.sign * fill.quantity
        marks[fill.symbol] = fill.base_price
        projected_cash = (
            self.cash_usd
            - fill.side.sign * fill.quantity * fill.base_price
            - fill.total_cost_usd
        )
        market_value = sum(quantity * marks[symbol] for symbol, quantity in quantities.items())
        gross = sum(abs(quantity * marks[symbol]) for symbol, quantity in quantities.items())
        equity = projected_cash + market_value
        return gross, equity

    def apply_fill(self, fill: Fill) -> tuple[Trade, ...]:
        normalized_time = self._validated_time(fill.timestamp_utc)
        if fill.fill_id <= self._last_fill_id:
            raise SimulationError("Fill IDs must be strictly increasing")
        projected_gross, projected_equity = self._projected_leverage(fill)
        if projected_equity <= 0:
            raise SimulationError("Fill would make portfolio equity non-positive")
        if projected_gross / projected_equity > self.max_leverage + 1e-9:
            raise SimulationError("Fill would exceed portfolio maximum leverage")
        self._last_timestamp = normalized_time
        self._last_fill_id = fill.fill_id
        signed = fill.side.sign * fill.quantity
        self.cash_usd -= signed * fill.base_price
        self.cash_usd -= fill.total_cost_usd
        self._total_costs_usd += fill.total_cost_usd
        self._marks[fill.symbol] = fill.base_price
        lots = self._lots.setdefault(fill.symbol, deque())
        remaining = signed
        created: list[Trade] = []
        fill_cost_per_share = fill.total_cost_usd / fill.quantity

        while remaining and lots and (lots[0].signed_quantity > 0) != (remaining > 0):
            lot = lots[0]
            close_quantity = min(abs(remaining), abs(lot.signed_quantity))
            if lot.signed_quantity > 0:
                gross = (fill.base_price - lot.price) * close_quantity
                trade_side = PositionSide.LONG
            else:
                gross = (lot.price - fill.base_price) * close_quantity
                trade_side = PositionSide.SHORT
            costs = (lot.entry_cost_per_share + fill_cost_per_share) * close_quantity
            net = gross - costs
            trade = Trade(
                trade_id=self._ids.next_trade(),
                symbol=fill.symbol,
                side=trade_side,
                quantity=close_quantity,
                entry_fill_id=lot.fill_id,
                exit_fill_id=fill.fill_id,
                entry_order_id=lot.order_id,
                exit_order_id=fill.order_id,
                entry_time_utc=lot.time_utc,
                exit_time_utc=fill.timestamp_utc,
                session_date=fill.timestamp_utc.astimezone(_ET).date(),
                entry_price=lot.price,
                exit_price=fill.base_price,
                gross_pnl_usd=round(gross, 10),
                costs_usd=round(costs, 10),
                net_pnl_usd=round(net, 10),
                holding_seconds=(fill.timestamp_utc - lot.time_utc).total_seconds(),
                exit_reason=fill.reason_code,
                tags=fill.tags,
            )
            self._realized_gross_usd += gross
            self._realized_by_symbol[fill.symbol] = self._realized_by_symbol.get(fill.symbol, 0.0) + gross
            self.trades.append(trade)
            created.append(trade)
            lot_sign = 1 if lot.signed_quantity > 0 else -1
            remaining_sign = 1 if remaining > 0 else -1
            lot.signed_quantity -= lot_sign * close_quantity
            remaining -= remaining_sign * close_quantity
            if lot.signed_quantity == 0:
                lots.popleft()

        if remaining:
            lots.append(
                _Lot(
                    signed_quantity=remaining,
                    price=fill.base_price,
                    fill_id=fill.fill_id,
                    order_id=fill.order_id,
                    time_utc=fill.timestamp_utc,
                    entry_cost_per_share=fill_cost_per_share,
                )
            )
        self.fills.append(fill)
        return tuple(created)

    def mark_to_market(self, prices: dict[str, float], timestamp_utc: datetime) -> PortfolioSnapshot:
        normalized_time = self._validated_time(timestamp_utc)
        for symbol, price in prices.items():
            if price <= 0:
                raise SimulationError(f"Invalid mark for {symbol}: {price}")
            self._marks[symbol] = price
        self._last_timestamp = normalized_time
        snapshot = self.snapshot(normalized_time)
        if snapshot.equity_usd <= 0:
            raise SimulationError("Mark-to-market produced non-positive equity")
        return snapshot

    def quantity(self, symbol: str) -> int:
        return sum(lot.signed_quantity for lot in self._lots.get(symbol.upper(), ()))

    def positions(self) -> tuple[Position, ...]:
        output: list[Position] = []
        for symbol in sorted(self._lots):
            lots = self._lots[symbol]
            quantity = sum(lot.signed_quantity for lot in lots)
            if quantity == 0:
                continue
            total_abs = sum(abs(lot.signed_quantity) for lot in lots)
            average = sum(abs(lot.signed_quantity) * lot.price for lot in lots) / total_abs
            mark = self._marks.get(symbol, average)
            unrealized = sum(
                (mark - lot.price) * lot.signed_quantity
                for lot in lots
            )
            output.append(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=average,
                    realized_pnl_usd=self._realized_by_symbol.get(symbol, 0.0),
                    unrealized_pnl_usd=unrealized,
                    last_price=mark,
                )
            )
        return tuple(output)

    def snapshot(self, timestamp_utc: datetime | None = None) -> PortfolioSnapshot:
        moment = timestamp_utc or self._last_timestamp or datetime.now(UTC)
        positions = self.positions()
        market_value = sum(position.quantity * position.last_price for position in positions)
        gross = sum(abs(position.quantity * position.last_price) for position in positions)
        unrealized = sum(position.unrealized_pnl_usd for position in positions)
        equity = self.cash_usd + market_value
        return PortfolioSnapshot(
            timestamp_utc=moment,
            cash_usd=round(self.cash_usd, 10),
            equity_usd=round(equity, 10),
            gross_exposure_usd=round(gross, 10),
            net_exposure_usd=round(market_value, 10),
            realized_pnl_usd=round(self._realized_gross_usd, 10),
            unrealized_pnl_usd=round(unrealized, 10),
            total_costs_usd=round(self._total_costs_usd, 10),
            positions=positions,
        )

    def reconcile(self) -> dict[str, float | bool]:
        snapshot = self.snapshot()
        expected_equity = self.initial_cash_usd + self._realized_gross_usd + snapshot.unrealized_pnl_usd - self._total_costs_usd
        return {
            "expected_equity_usd": round(expected_equity, 8),
            "actual_equity_usd": round(snapshot.equity_usd, 8),
            "difference_usd": round(snapshot.equity_usd - expected_equity, 8),
            "reconciled": abs(snapshot.equity_usd - expected_equity) < 1e-6,
        }
