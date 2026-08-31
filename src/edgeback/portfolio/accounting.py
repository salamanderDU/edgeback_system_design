"""
Pure portfolio accounting helpers.

This module centralizes the documented MVP accounting policy:

- ``fill_price`` on :class:`edgeback.domain.fills.Fill` is the **base execution
  price**. The adverse synthetic spread/slippage is carried separately on the
  fill (``spread_usd``, ``slippage_usd``) and combined with ``commission_usd``
  into the net cash effect.
- Money values (cash, P&L, costs) are rounded to cents with
  ``ROUND_HALF_UP`` through :func:`round_money`. Prices/quantities remain
  float64, matching the domain models.
- Position quantities are **signed net shares**: positive = long,
  negative = short. ``average_price`` is the weighted-average base execution
  price of the open net position.
- Realized P&L is computed on a closed portion at **base execution prices**:
  ``(exit_base_price - entry_average_base_price) * closed_shares`` for a long
  reduction, and ``(short_average_base_price - cover_base_price) *
  covered_shares`` for a short cover. Spread, slippage, and commission are all
  expensed through cash (see :func:`cash_delta_for_fill`), so equity remains
  ``cash + sum(signed_shares * mark)`` and a flat round trip satisfies
  ``cash_change = realized_pnl - total_costs``.
- :func:`effective_price` is the informational per-fill **effective execution**
  decomposition described in ``docs/04_BACKTEST_ENGINE.md`` §6 (base price
  plus adverse spread/slippage and commission). It is **not** used for
  realized P&L; costs are tracked separately through cash.
- :func:`project_fills` is an independent, stateless replay of a fill sequence
  used by :func:`edgeback.portfolio.ledger.PortfolioLedger.reconcile` to verify
  the ledger's accounting invariants.

These helpers never mutate external state and never perform network I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from edgeback.domain.fills import Fill

MONEY_PRECISION = Decimal("0.01")
AVG_PRICE_PRECISION = 10


def round_money(value: float) -> float:
    """Round a money value to cents using ``ROUND_HALF_UP``."""
    return float(Decimal(str(value)).quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP))


def is_direction_buy(fill: Fill) -> bool:
    """A buy action increases the signed net position (covers shorts too)."""
    return fill.action == "buy"


def signed_quantity(fill: Fill) -> int:
    """Signed net-share quantity contribution: ``+shares`` for buys, ``-shares`` for sells."""
    return fill.shares if is_direction_buy(fill) else -fill.shares


def effective_price(fill: Fill) -> float:
    """
    Informational per-fill effective execution price (docs/04 §6).

    ``base_price +/- adverse spread/slippage + commission`` on a per-share
    basis. This is the documented cost decomposition for a fill, not the basis
    for realized P&L, which uses base prices with all costs flowing through
    cash.
    """
    per_share_cost = (fill.spread_usd + fill.slippage_usd + fill.commission_usd) / fill.shares
    adverse = per_share_cost if is_direction_buy(fill) else -per_share_cost
    return fill.fill_price + adverse


def total_fill_cost_usd(fill: Fill) -> float:
    """Total USD cost of a fill: spread + slippage + commission."""
    return fill.spread_usd + fill.slippage_usd + fill.commission_usd


def cash_delta_for_fill(fill: Fill) -> float:
    """
    Net cash change for applying a fill (signed; negative = cash out).

    A buy pays ``shares * base_price`` plus costs; a sell receives
    ``shares * base_price`` less costs. Equivalently,
    ``-signed_quantity * base_price - total_costs``.
    """
    return -signed_quantity(fill) * fill.fill_price - total_fill_cost_usd(fill)


def weighted_average(
    current_qty: float,
    current_avg: float,
    add_qty: float,
    add_price: float,
) -> float:
    """Weighted-average price of two legs; assumes ``add_qty > 0``."""
    total_qty = current_qty + add_qty
    if total_qty <= 0:
        return 0.0
    return round((current_qty * current_avg + add_qty * add_price) / total_qty, AVG_PRICE_PRECISION)


@dataclass(frozen=True)
class ProjectedPosition:
    """Independent projection of an open net position."""

    symbol: str
    shares: int = 0
    average_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class ProjectionResult:
    """Result of an independent replay of a fill sequence."""

    cash: float
    positions: Mapping[str, ProjectedPosition]
    realized_pnl: float
    total_commission_usd: float
    total_spread_usd: float
    total_slippage_usd: float
    fill_count: int

    @property
    def total_costs_usd(self) -> float:
        return self.total_commission_usd + self.total_spread_usd + self.total_slippage_usd


def _apply_buy(
    pos: ProjectedPosition,
    fill: Fill,
    realized_accum: list[float],
) -> ProjectedPosition:
    """Apply a buy fill to a projected position; appends realized P&L if closing shorts."""
    qty = fill.shares
    base = fill.fill_price
    shares = pos.shares
    avg = pos.average_price

    if shares >= 0:
        # Add to an existing long or open a long from flat.
        new_avg = weighted_average(shares, avg, qty, base)
        return ProjectedPosition(
            symbol=pos.symbol,
            shares=shares + qty,
            average_price=new_avg,
            realized_pnl=pos.realized_pnl,
        )

    # Currently short: the buy covers up to the short size, then flips to long.
    # Realized uses base prices; the cover fill's costs flow through cash.
    cover = min(qty, -shares)
    realized_accum[0] = round_money(realized_accum[0] + round_money(cover * (avg - base)))
    new_shares = shares + qty
    if new_shares > 0:
        # Flipped to long; the excess shares were acquired at `base`.
        new_avg = round(base, AVG_PRICE_PRECISION)
    else:
        new_avg = 0.0 if new_shares == 0 else avg
    return ProjectedPosition(
        symbol=pos.symbol,
        shares=new_shares,
        average_price=new_avg,
        realized_pnl=pos.realized_pnl,
    )


def _apply_sell(
    pos: ProjectedPosition,
    fill: Fill,
    realized_accum: list[float],
) -> ProjectedPosition:
    """Apply a sell fill to a projected position; appends realized P&L if closing longs."""
    qty = fill.shares
    base = fill.fill_price
    shares = pos.shares
    avg = pos.average_price

    if shares <= 0:
        # Add to an existing short or open a short from flat.
        short_qty = -shares
        new_avg = weighted_average(short_qty, avg, qty, base)
        return ProjectedPosition(
            symbol=pos.symbol,
            shares=shares - qty,
            average_price=new_avg,
            realized_pnl=pos.realized_pnl,
        )

    # Currently long: the sell closes up to the long size, then flips to short.
    # Realized uses base prices; the exit fill's costs flow through cash.
    close = min(qty, shares)
    realized_accum[0] = round_money(realized_accum[0] + round_money(close * (base - avg)))
    new_shares = shares - qty
    if new_shares < 0:
        # Flipped to short; the excess shares were sold at `base`.
        new_avg = round(base, AVG_PRICE_PRECISION)
    else:
        new_avg = avg if new_shares > 0 else 0.0
    return ProjectedPosition(
        symbol=pos.symbol,
        shares=new_shares,
        average_price=new_avg,
        realized_pnl=pos.realized_pnl,
    )


def project_fills(initial_cash: float, fills: Iterable[Fill]) -> ProjectionResult:
    """
    Independently replay a sequence of fills into cash, positions, and realized P&L.

    No timezone/monotonicity/order-id guards are applied here; the ledger
    performs those at fill-application time. This is the double-entry
    verification used by ``reconcile``.
    """
    cash = round_money(initial_cash)
    positions: dict[str, ProjectedPosition] = {}
    realized_accum = [0.0]
    total_commission = 0.0
    total_spread = 0.0
    total_slippage = 0.0
    count = 0

    for fill in fills:
        cash = round_money(cash + cash_delta_for_fill(fill))
        total_commission = round_money(total_commission + fill.commission_usd)
        total_spread = round_money(total_spread + fill.spread_usd)
        total_slippage = round_money(total_slippage + fill.slippage_usd)
        count += 1

        current = positions.get(fill.symbol, ProjectedPosition(symbol=fill.symbol))
        if is_direction_buy(fill):
            next_pos = _apply_buy(current, fill, realized_accum)
        else:
            next_pos = _apply_sell(current, fill, realized_accum)
        positions[fill.symbol] = next_pos

    return ProjectionResult(
        cash=round_money(cash),
        positions=positions,
        realized_pnl=round_money(realized_accum[0]),
        total_commission_usd=total_commission,
        total_spread_usd=total_spread,
        total_slippage_usd=total_slippage,
        fill_count=count,
    )
