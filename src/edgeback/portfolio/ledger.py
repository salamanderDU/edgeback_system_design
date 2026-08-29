"""
Mutable portfolio ledger for the EdgeBack engine.

The ledger is the **only** component that changes cash and positions
(``docs/02_ARCHITECTURE.md`` §4). Fills are immutable events applied through
:meth:`PortfolioLedger.apply_fill`; mark-to-market happens through
:meth:`PortfolioLedger.mark_to_market`.

Accounting model
----------------
- Positions are tracked as signed net shares. ``average_price`` is the
  weighted-average **base** execution price of the open net position. Spread,
  slippage, and commission are costs paid from cash; realized P&L from closing
  a portion is ``(exit_base - entry_avg_base) * closed_shares`` for longs and
  ``(short_avg_base - cover_base) * covered_shares`` for shorts. Per-fill
  spread/slippage/commission decomposition is carried on each
  :class:`~edgeback.domain.fills.Fill` and expensed through cash, matching
  ``docs/04_BACKTEST_ENGINE.md`` §6.
- Equity is ``cash + sum(signed_shares * mark_price)`` at the current
  valuation (``docs/04_BACKTEST_ENGINE.md`` §7).
- All timestamps are timezone-aware UTC. Fills must arrive in non-decreasing
  order of ``timestamp_utc``. An optional engine-level ``order_id`` monotonic
  counter guards against out-of-order application from the event loop; equal
  order ids are permitted for later multi-leg bracket fills.
- All guards (cash minimum and maximum leverage) are evaluated **before** any
  mutation, so a rejected fill never leaves the ledger half-applied.

Reconciliation
--------------
:meth:`reconcile` replays the whole applied-fill history through the
independent :func:`edgeback.portfolio.accounting.project_fills` and asserts
equal cash, positions, realized P&L, and cost totals.

:class:`ReconciliationReport` records the invariant results for run artifacts;
a failure is ``reconciled=False`` with ``position_differences`` details.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from edgeback.domain.fills import Fill
from edgeback.domain.positions import PortfolioSnapshot, Position
from edgeback.portfolio.accounting import (
    cash_delta_for_fill,
    is_direction_buy,
    project_fills,
    round_money,
    signed_quantity,
    weighted_average,
)

__all__ = [
    "PortfolioLedger",
    "LedgerPosition",
    "ReconciliationReport",
    "AccountingError",
]


class AccountingError(Exception):
    """Raised when a fill would violate a documented portfolio invariant."""


@dataclass
class LedgerPosition:
    """Per-symbol open position tracked by the ledger."""

    symbol: str
    shares: int = 0
    average_price: float = 0.0
    realized_pnl: float = 0.0
    estimated_risk: float = 0.0


@dataclass(frozen=True)
class ReconciliationReport:
    """Results of reconciling the ledger against an independent replay."""

    reconciled: bool
    cash: float
    projected_cash: float
    cash_difference: float
    realized_pnl: float
    projected_realized_pnl: float
    position_differences: Mapping[str, str]
    fill_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "reconciled": self.reconciled,
            "cash": self.cash,
            "projected_cash": self.projected_cash,
            "cash_difference": self.cash_difference,
            "realized_pnl": self.realized_pnl,
            "projected_realized_pnl": self.projected_realized_pnl,
            "position_differences": dict(self.position_differences),
            "fill_count": self.fill_count,
        }


class PortfolioLedger:
    """
    Deterministic portfolio state machine.

    Parameters
    ----------
    initial_cash
        Starting USD cash balance.
    max_leverage
        Maximum ``gross_exposure / equity`` before a fill is rejected. ``None``
        disables the leverage guard.
    min_cash
        Lowest permitted cash balance. ``None`` disables the cash guard.
    """

    def __init__(
        self,
        initial_cash: float,
        max_leverage: float | None = 1.0,
        min_cash: float | None = 0.0,
    ) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if max_leverage is not None and max_leverage <= 0:
            raise ValueError("max_leverage must be positive when set")
        if min_cash is not None and min_cash < 0:
            raise ValueError("min_cash cannot be negative when set")

        self._initial_cash = round_money(initial_cash)
        self._cash = round_money(initial_cash)
        self._max_leverage = max_leverage
        self._min_cash = min_cash
        self._positions: dict[str, LedgerPosition] = {}
        self._marks: dict[str, float] = {}
        self._last_fill_ts: datetime | None = None
        self._last_order_id: int | None = None
        self._applied_fills: list[Fill] = []
        self._realized_pnl = 0.0
        self._total_commission_usd = 0.0
        self._total_spread_usd = 0.0
        self._total_slippage_usd = 0.0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def initial_cash(self) -> float:
        return self._initial_cash

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def last_fill_timestamp_utc(self) -> datetime | None:
        return self._last_fill_ts

    @property
    def last_order_id(self) -> int | None:
        return self._last_order_id

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def total_commission_usd(self) -> float:
        return self._total_commission_usd

    @property
    def total_spread_usd(self) -> float:
        return self._total_spread_usd

    @property
    def total_slippage_usd(self) -> float:
        return self._total_slippage_usd

    @property
    def total_costs_usd(self) -> float:
        return self._total_commission_usd + self._total_spread_usd + self._total_slippage_usd

    @property
    def applied_fill_count(self) -> int:
        return len(self._applied_fills)

    def applied_fills(self) -> list[Fill]:
        """Immutable copy of every fill applied to this ledger."""
        return list(self._applied_fills)

    # ------------------------------------------------------------------
    # Portfolio state
    # ------------------------------------------------------------------

    def positions(self) -> dict[str, Position]:
        """Snapshot of current positions using the latest mark prices."""
        return {
            symbol: Position(
                symbol=symbol,
                shares=pos.shares,
                average_price=pos.average_price,
                realized_pnl=round_money(pos.realized_pnl),
                unrealized_pnl=round_money(self.unrealized_pnl(symbol)),
            )
            for symbol, pos in sorted(self._positions.items())
        }

    def snapshot(self) -> PortfolioSnapshot:
        """Portfolio snapshot at current marks (see ``docs/02`` §6)."""
        return PortfolioSnapshot(
            cash=round_money(self._cash),
            equity=round_money(self.equity()),
            gross_exposure=round_money(self.gross_exposure()),
            net_exposure=round_money(self.net_exposure()),
        )

    def position(self, symbol: str) -> Position:
        """Current position for ``symbol`` (flat Position when none exists)."""
        pos = self._positions.get(symbol)
        if pos is None:
            return Position(symbol=symbol, shares=0, average_price=0.0)
        return Position(
            symbol=symbol,
            shares=pos.shares,
            average_price=pos.average_price,
            realized_pnl=round_money(pos.realized_pnl),
            unrealized_pnl=round_money(self.unrealized_pnl(symbol)),
        )

    def mark_price(self, symbol: str) -> float | None:
        """Latest valuation price for ``symbol`` or ``None`` if unmarked."""
        return self._marks.get(symbol)

    def unrealized_pnl(self, symbol: str) -> float:
        """Unrealized P&L at the current mark; zero when unmarked or flat."""
        pos = self._positions.get(symbol)
        if pos is None or pos.shares == 0:
            return 0.0
        mark = self._marks.get(symbol)
        if mark is None:
            return 0.0
        return round_money(pos.shares * (mark - pos.average_price))

    def equity(self) -> float:
        """Equity = cash + sum(signed_shares * mark)."""
        marked = sum(
            pos.shares * self._marks.get(symbol, pos.average_price)
            for symbol, pos in self._positions.items()
        )
        return round_money(self._cash + marked)

    def gross_exposure(self) -> float:
        """Absolute sum of position notional at current marks/averages."""
        return round_money(
            sum(
                abs(pos.shares) * self._marks.get(symbol, pos.average_price)
                for symbol, pos in self._positions.items()
            )
        )

    def net_exposure(self) -> float:
        """Signed sum of position notional at current marks/averages."""
        return round_money(
            sum(
                pos.shares * self._marks.get(symbol, pos.average_price)
                for symbol, pos in self._positions.items()
            )
        )

    def leverage(self) -> float:
        """Gross exposure divided by equity; zero when equity is not positive."""
        equity = self.equity()
        if equity <= 0:
            return 0.0
        return self.gross_exposure() / equity

    def is_flat(self) -> bool:
        return all(pos.shares == 0 for pos in self._positions.values())

    # ------------------------------------------------------------------
    # State mutation
    # ------------------------------------------------------------------

    def mark_to_market(self, symbol: str, price: float) -> None:
        """Set the valuation price for ``symbol`` (may be a bar close)."""
        if price <= 0:
            raise ValueError("mark price must be positive")
        self._marks[symbol] = price

    def apply_fill(self, fill: Fill, order_id: int | None = None) -> None:
        """
        Apply an immutable fill to the ledger.

        ``order_id`` is an optional engine-level monotonic counter used to guard
        against out-of-order application from the event loop. When provided it
        must not be lower than the last seen order id (equal ids are allowed to
        support later multi-leg bracket fills).
        """
        self._validate_fill_order(fill, order_id)

        # Evaluate all accounting guards against the *projected* state first.
        # A rejected fill must never leave the ledger half-applied.
        projected_cash = round_money(self._cash + cash_delta_for_fill(fill))
        self._check_cash_guard(fill, projected_cash)
        self._check_leverage_guard(fill)

        # Apply effects.
        self._cash = projected_cash
        self._total_commission_usd = round_money(self._total_commission_usd + fill.commission_usd)
        self._total_spread_usd = round_money(self._total_spread_usd + fill.spread_usd)
        self._total_slippage_usd = round_money(self._total_slippage_usd + fill.slippage_usd)

        pos = self._positions.setdefault(fill.symbol, LedgerPosition(symbol=fill.symbol))
        self._apply_fill_to_position(pos, fill)

        self._applied_fills.append(fill)
        self._last_fill_ts = fill.timestamp_utc
        if order_id is not None:
            self._last_order_id = order_id

    # ------------------------------------------------------------------
    # Fill validation and guards
    # ------------------------------------------------------------------

    def _validate_fill_order(self, fill: Fill, order_id: int | None) -> None:
        ts = fill.timestamp_utc
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise AccountingError("fill timestamp must be timezone-aware UTC")

        if self._last_fill_ts is not None and ts < self._last_fill_ts:
            raise AccountingError(
                "fill timestamp moves backwards: "
                f"{ts.isoformat()} < {self._last_fill_ts.isoformat()}"
            )

        if order_id is not None:
            if self._last_order_id is not None and order_id < self._last_order_id:
                raise AccountingError(
                    f"order id moves backwards: {order_id} < {self._last_order_id}"
                )

        if fill.shares <= 0:
            raise AccountingError("fill shares must be positive")

    def _check_cash_guard(self, fill: Fill, projected_cash: float) -> None:
        """Reject fills that would violate the configured cash minimum."""
        if self._min_cash is None:
            return
        if projected_cash < round_money(self._min_cash):
            raise AccountingError(
                "fill would violate minimum cash: "
                f"projected_cash={projected_cash} < min_cash={self._min_cash}"
            )

    def _check_leverage_guard(self, fill: Fill) -> None:
        """
        Reject a fill whose projected gross exposure exceeds the leverage limit.

        The projection marks the filled quantity at the fill's base price
        (``signed_quantity(fill) * fill.fill_price``) and carries the rest of
        the book at current marks. Cash uses the projected figure so the new
        equity is consistent with the post-fill state.
        """
        if self._max_leverage is None:
            return

        symbol = fill.symbol
        pos = self._positions.get(symbol, LedgerPosition(symbol=symbol))
        new_shares = pos.shares + signed_quantity(fill)
        projected_gross_from_symbol = abs(new_shares) * fill.fill_price
        projected_gross = sum(
            abs(other.shares) * self._marks.get(other_symbol, other.average_price)
            for other_symbol, other in self._positions.items()
            if other_symbol != symbol
        )
        projected_gross = round_money(projected_gross + projected_gross_from_symbol)

        projected_cash = round_money(self._cash + cash_delta_for_fill(fill))
        projected_equity = round_money(
            projected_cash
            + (
                new_shares * fill.fill_price
                + sum(
                    other.shares * self._marks.get(other_symbol, other.average_price)
                    for other_symbol, other in self._positions.items()
                    if other_symbol != symbol
                )
            )
        )

        if projected_equity <= 0 or projected_gross > self._max_leverage * projected_equity:
            raise AccountingError(
                "fill would violate maximum leverage: "
                f"projected_gross_exposure={projected_gross} > "
                f"leverage_limit={self._max_leverage * projected_equity}"
            )

    # ------------------------------------------------------------------
    # Position bookkeeping
    # ------------------------------------------------------------------

    def _apply_fill_to_position(self, pos: LedgerPosition, fill: Fill) -> None:
        """Apply cash-independent position effects (shares, average, realized P&L)."""
        # Realized P&L uses the fill's base price; spread/slippage/commission
        # were already expensed through cash as the fill was applied.
        if is_direction_buy(fill):
            self._apply_buy(pos, fill)
        else:
            self._apply_sell(pos, fill)

    def _apply_buy(self, pos: LedgerPosition, fill: Fill) -> None:
        if pos.shares >= 0:
            # Add to an existing long or open a long from flat.
            pos.average_price = weighted_average(
                pos.shares, pos.average_price, fill.shares, fill.fill_price
            )
            pos.shares += fill.shares
            return

        # Currently short: the buy covers up to the short size, then flips.
        cover = min(fill.shares, -pos.shares)
        gain = round_money(cover * (pos.average_price - fill.fill_price))
        self._record_realized(gain, pos)
        pos.shares += fill.shares
        if pos.shares > 0:
            # Flipped to long; the excess shares were acquired at this buy price.
            pos.average_price = round(fill.fill_price, 10)
        elif pos.shares == 0:
            pos.average_price = 0.0
        # else: short remains open with its original weighted-average price.

    def _apply_sell(self, pos: LedgerPosition, fill: Fill) -> None:
        if pos.shares <= 0:
            # Add to an existing short or open a short from flat.
            short_qty = -pos.shares
            pos.average_price = weighted_average(
                short_qty, pos.average_price, fill.shares, fill.fill_price
            )
            pos.shares -= fill.shares
            return

        # Currently long: the sell closes up to the long size, then flips.
        close = min(fill.shares, pos.shares)
        gain = round_money(close * (fill.fill_price - pos.average_price))
        self._record_realized(gain, pos)
        pos.shares -= fill.shares
        if pos.shares < 0:
            # Flipped to short; the excess shares were sold at this price.
            pos.average_price = round(fill.fill_price, 10)
        elif pos.shares == 0:
            pos.average_price = 0.0

    def _record_realized(self, gain: float, pos: LedgerPosition) -> None:
        self._realized_pnl = round_money(self._realized_pnl + gain)
        pos.realized_pnl = round_money(pos.realized_pnl + gain)

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile(self) -> ReconciliationReport:
        """Replay the applied fills independently and compare ledgers."""
        projected = project_fills(self._initial_cash, self._applied_fills)

        diffs: dict[str, str] = {}
        for symbol, proj_pos in projected.positions.items():
            pos = self._positions.get(symbol, LedgerPosition(symbol=symbol))
            if pos.shares != proj_pos.shares:
                diffs[symbol] = f"shares {pos.shares} != {proj_pos.shares}"
            elif abs(pos.average_price - proj_pos.average_price) > 0.000001:
                diffs[symbol] = f"avg_price {pos.average_price} != {proj_pos.average_price}"

        for symbol in set(self._positions) - set(projected.positions):
            pos = self._positions[symbol]
            if pos.shares != 0:
                diffs[symbol] = f"ledger holds {pos.shares} shares not seen in replay"

        cash_diff = round_money(self._cash - projected.cash)
        realized_diff = round_money(self._realized_pnl - projected.realized_pnl)
        cost_diff = round_money(self.total_costs_usd - projected.total_costs_usd)

        reconciled = bool(
            not diffs
            and cash_diff == 0.0
            and realized_diff == 0.0
            and cost_diff == 0.0
            and self.applied_fill_count == projected.fill_count
        )

        return ReconciliationReport(
            reconciled=reconciled,
            cash=round_money(self._cash),
            projected_cash=projected.cash,
            cash_difference=cash_diff,
            realized_pnl=round_money(self._realized_pnl),
            projected_realized_pnl=projected.realized_pnl,
            position_differences=diffs,
            fill_count=self.applied_fill_count,
        )
