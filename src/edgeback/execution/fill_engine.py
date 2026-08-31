"""
Deterministic order-matching and lifecycle engine (T420).

Implements ``docs/04_BACKTEST_ENGINE.md`` §4-5 semantics:

- A market order becomes eligible on the next bar and fills at that bar's open.
- Buy/sell limits: if the bar opens on the favorable side the base fill is the
  open (better of open/limit); otherwise a touch of the limit price fills at
  the limit.
- Buy/sell stops: if the bar opens through the stop the base fill is the open
  (gap-through); otherwise a touch fills at the stop.
- Bracket orders activate their stop-loss and take-profit children when the
  entry fills at the bar open; the children are active for the remainder of
  that same bar with the configured same-bar ambiguity policy
  (``stop_first`` default, ``target_first``, ``nearest_to_open``,
  ``reject_ambiguous_bar``).
- Unfilled orders expire when a bar starts after ``expires_at_utc`` and are
  never backfilled.
- Orders are evaluated deterministically by ``(-priority, symbol,
  creation_sequence)``.

Each produced :class:`~edgeback.domain.fills.Fill` carries the T410 cost
decomposition (spread/slippage/commission) computed from the order's base
fill price, ready for the T400 portfolio ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from edgeback.domain.bars import Bar
from edgeback.domain.fills import Fill
from edgeback.domain.orders import Order, OrderEvent
from edgeback.domain.positions import Position
from edgeback.execution.costs import ExecutionCosts

__all__ = [
    "SimulatedBroker",
    "FillEngineError",
    "OrderEvaluation",
]


class FillEngineError(Exception):
    """Raised when an operation would violate the order lifecycle."""


@dataclass(frozen=True)
class OrderEvaluation:
    """Result of evaluating one order against one bar (or ``None`` when unmatched)."""

    order: Order
    bar: Bar
    base_price: float | None


class SimulatedBroker:
    """
    A deterministic simulated broker matching a working order book against bars.

    Parameters
    ----------
    costs
        T410 execution-cost bundle used to decompose each fill.
    same_bar_policy
        ``stop_first`` | ``target_first`` | ``nearest_to_open`` |
        ``reject_ambiguous_bar`` (docs/04 §5).
    """

    def __init__(self, costs: ExecutionCosts, same_bar_policy: str = "stop_first") -> None:
        if same_bar_policy not in {
            "stop_first",
            "target_first",
            "nearest_to_open",
            "reject_ambiguous_bar",
        }:
            raise ValueError(f"unknown same-bar policy: {same_bar_policy}")
        self._costs = costs
        self._same_bar_policy = same_bar_policy
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._events: list[OrderEvent] = []
        self._warnings: list[str] = []
        self._order_seq: int = 0
        self._fill_seq: int = 0
        self._clock: datetime | None = None

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def fills(self) -> list[Fill]:
        """All fills produced so far, in creation order."""
        return list(self._fills)

    @property
    def events(self) -> list[OrderEvent]:
        """All order lifecycle events, in creation order."""
        return list(self._events)

    @property
    def warnings(self) -> list[str]:
        """Deterministic research warnings (e.g. ambiguous-bar rejection)."""
        return list(self._warnings)

    def orders(self) -> list[Order]:
        """All orders known to the broker, sorted by creation sequence."""
        return [
            self._orders[o]
            for o in sorted(self._orders, key=lambda k: self._orders[k].creation_sequence)
        ]

    def open_orders(self) -> list[Order]:
        """Orders that are still working (``open`` status)."""
        return [o for o in self.orders() if o.status == "open"]

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    # ------------------------------------------------------------------
    # Submission / cancellation
    # ------------------------------------------------------------------

    def submit(self, order: Order, now_utc: datetime | None = None) -> Order:
        """Accept a pending order into the working book."""
        if order.id in self._orders:
            raise FillEngineError(f"order {order.id} already exists")
        if order.status != "pending":
            raise FillEngineError(
                f"order {order.id} must be pending to submit (got {order.status})"
            )
        if order.eligible_from_utc is None:
            raise FillEngineError(f"order {order.id} must declare eligible_from_utc")
        eligible = order.eligible_from_utc
        if order.creation_sequence > 0:
            self._order_seq = max(self._order_seq, order.creation_sequence)
        seq = order.creation_sequence or self._next_seq()
        accepted = order.model_copy(update={"status": "open", "creation_sequence": seq})
        self._orders[accepted.id] = accepted
        self._emit(accepted, "accepted", now_utc or eligible)
        return accepted

    def cancel(self, order_id: str, now_utc: datetime, reason: str) -> Order:
        """Cancel an open order with an explicit reason."""
        order = self._orders.get(order_id)
        if order is None:
            raise FillEngineError(f"unknown order: {order_id}")
        if order.status != "open":
            raise FillEngineError(f"order {order_id} is not open (status={order.status})")
        cancelled = order.model_copy(update={"status": "cancelled", "reason": reason})
        self._orders[order_id] = cancelled
        self._emit(cancelled, "cancelled", now_utc)
        return cancelled

    # ------------------------------------------------------------------
    # Bar processing
    # ------------------------------------------------------------------

    def on_bars(self, bars: list[Bar]) -> list[Fill]:
        """Process bars in chronological order; return fills in creation order."""
        produced: list[Fill] = []
        for bar in sorted(bars, key=lambda b: b.bar_end_utc):
            produced.extend(self.on_bar(bar))
        return produced

    def on_bar(self, bar: Bar) -> list[Fill]:
        """Evaluate the working book against one completed bar.

        Only orders whose ``order.symbol`` equals ``bar.symbol`` are evaluated
        (ADR-013): without this filter a working order for one symbol could
        match (and fill on) another symbol's bar prices in multi-symbol runs.
        """
        self._advance_clock(bar.bar_end_utc)
        self._expire_unfilled(bar)
        produced: list[Fill] = []

        for order in self._order_eval_sequence():
            if order.status != "open" or order.symbol != bar.symbol:
                continue
            if not self._is_eligible(order, bar):
                continue
            base = self._match_base_price(order, bar)
            if base is None:
                continue
            fill = self._make_fill(order, base, bar.bar_end_utc)
            produced.append(fill)
            self._record_fill(order, fill, bar)
            if order.order_type == "bracket":
                produced.extend(self._activate_bracket_children(order, bar))
        return produced

    def force_flat_at_close(self, positions: Mapping[str, Position], bar: Bar) -> list[Fill]:
        """
        Engine-generated forced session-close liquidation (docs/04 §10).

        For every open position for ``bar.symbol`` on the final regular-session
        bar, build a deterministic market order that closes the position at the
        **bar close** plus adverse spread/slippage and commission, tagged
        ``FORCED_SESSION_CLOSE``. Any still-open protective children belonging
        to the closed position's bracket are cancelled with
        ``FORCED_SESSION_CLOSE_PARENT`` so they cannot fill later in the same
        session.

        This is the *only* documented same-close fill (ADR-007) and is never
        triggered by a strategy signal: the engine calls it after strategy
        dispatch, so a strategy cannot inspect the final close and request a
        same-close fill of its own.
        """
        self._advance_clock(bar.bar_end_utc)
        produced: list[Fill] = []
        for symbol, pos in sorted(positions.items()):
            if symbol != bar.symbol or pos.shares == 0:
                continue
            is_long = pos.shares > 0
            fill_action: Literal["buy", "sell"] = "sell" if is_long else "buy"
            seq = self._next_seq()
            order = Order(
                id=f"{symbol}-force-{seq}",
                symbol=symbol,
                direction="long" if is_long else "short",
                order_type="market",
                shares=abs(pos.shares),
                status="open",
                eligible_from_utc=bar.bar_end_utc,
                creation_sequence=seq,
                priority=0,
                reason="FORCED_SESSION_CLOSE",
            )
            self._orders[order.id] = order
            self._emit(order, "accepted", bar.bar_end_utc)
            # Base fill is the final-bar close (the documented exception); the
            # cost bundle applies adverse spread/slippage and commission.
            fill = self._make_fill(order, bar.close, bar.bar_end_utc, action=fill_action)
            self._record_fill(order, fill, bar)
            # The position is flat now; cancel any leftover protective children.
            self._cancel_open_children_for_symbol(symbol, bar)
            self._warnings.append(
                f"FORCED_SESSION_CLOSE at {bar.bar_end_utc.isoformat()} symbol={symbol}: "
                f"{abs(pos.shares)} shares liquidated at close {bar.close}"
            )
            produced.append(fill)
        return produced

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._order_seq += 1
        return self._order_seq

    def _next_fill_id(self) -> str:
        self._fill_seq += 1
        return f"fill-{self._fill_seq}"

    def _advance_clock(self, ts: datetime) -> None:
        if self._clock is not None and ts < self._clock:
            raise FillEngineError(
                f"broker clock moves backwards: {ts.isoformat()} < {self._clock.isoformat()}"
            )
        self._clock = ts

    def _emit(self, order: Order, event_type: str, ts_utc: datetime) -> None:
        self._events.append(
            OrderEvent(
                order=order,
                event_type=event_type,  # type: ignore[arg-type]
                timestamp_utc=ts_utc.isoformat(),
                reason=order.reason,
            )
        )

    def _order_eval_sequence(self) -> list[Order]:
        return sorted(
            self._orders.values(),
            key=lambda o: (-o.priority, o.symbol, o.creation_sequence),
        )

    def _is_eligible(self, order: Order, bar: Bar) -> bool:
        """
        An order is eligible for a bar when that bar **starts** at/after its
        eligibility time. An order with ``eligible_from = next_bar_start``
        therefore cannot fill on the bar whose close produced the signal.
        """
        if order.eligible_from_utc is None:
            return False
        return bar.bar_start_utc >= order.eligible_from_utc

    def _expire_unfilled(self, bar: Bar) -> None:
        """Cancel open orders whose expiry is before the start of this bar."""
        for order in list(self._orders.values()):
            if (
                order.status == "open"
                and order.expires_at_utc is not None
                and bar.bar_start_utc > order.expires_at_utc
            ):
                cancelled = order.model_copy(
                    update={"status": "cancelled", "reason": "ORDER_EXPIRED"}
                )
                self._orders[order.id] = cancelled
                self._emit(cancelled, "cancelled", bar.bar_end_utc)

    # ------------------------------------------------------------------
    # Order-type matching (docs/04 §4)
    # ------------------------------------------------------------------

    def _action_for(self, order: Order) -> Literal["buy", "sell"]:
        """Map an order to its fill action (buy/sell)."""
        is_exit = order.parent_order_id is not None
        if order.direction == "long":
            return "sell" if is_exit else "buy"
        return "buy" if is_exit else "sell"

    def _match_base_price(self, order: Order, bar: Bar) -> float | None:
        """Return the base execution price when the order matches this bar, else ``None``."""
        order_type = order.order_type
        if order_type == "market":
            return bar.open

        if order_type == "limit":
            limit = order.limit_price
            if limit is None:
                raise FillEngineError(f"limit order {order.id} missing limit_price")
            if self._action_for(order) == "buy":
                if bar.open <= limit:
                    return bar.open
                return limit if bar.low <= limit else None
            if bar.open >= limit:
                return bar.open
            return limit if bar.high >= limit else None

        if order_type == "stop":
            stop = order.stop_price
            if stop is None:
                raise FillEngineError(f"stop order {order.id} missing stop_price")
            if self._action_for(order) == "buy":
                if bar.open >= stop:
                    return bar.open  # gap through
                return stop if bar.high >= stop else None
            if bar.open <= stop:
                return bar.open  # gap through
            return stop if bar.low <= stop else None

        if order_type == "bracket":
            # Bracket entries behave like market entries eligible at next bar.
            return bar.open

        raise FillEngineError(f"unsupported order type: {order.order_type}")

    # ------------------------------------------------------------------
    # Fill production
    # ------------------------------------------------------------------

    def _make_fill(
        self,
        order: Order,
        base_price: float,
        ts_utc: datetime,
        action: Literal["buy", "sell"] | None = None,
    ) -> Fill:
        # ``action`` is inferred from the order's entry/exit role, except for
        # engine-generated forced-close orders where the caller supplies it
        # explicitly (closing a long is a sell even without a parent order).
        fill_action = action if action is not None else self._action_for(order)
        deco = self._costs.decompose(base_price=base_price, shares=order.shares, action=fill_action)
        return Fill(
            id=self._next_fill_id(),
            order_id=order.id,
            symbol=order.symbol,
            timestamp_utc=ts_utc,
            direction=order.direction,
            action=fill_action,
            shares=order.shares,
            fill_price=base_price,
            commission_usd=deco.commission_usd,
            slippage_usd=deco.slippage_usd,
            spread_usd=deco.spread_usd,
            reason=order.reason or "market_fill",
        )

    def _record_fill(self, order: Order, fill: Fill, bar: Bar) -> None:
        filled = order.model_copy(update={"status": "filled", "reason": fill.reason})
        self._orders[order.id] = filled
        self._fills.append(fill)
        self._emit(filled, "filled", bar.bar_end_utc)
        # A protective child that fills (in the same bar or a later bar) cancels
        # its sibling so the sibling cannot fill again on a later bar.
        self._cancel_sibling_children(order, bar)

    # ------------------------------------------------------------------
    # Bracket children
    # ------------------------------------------------------------------

    def _activate_bracket_children(self, entry: Order, bar: Bar) -> list[Fill]:
        """
        Activate the stop-loss and take-profit children for an entry that
        filled at this bar's open; children are active for the remainder of
        the bar (docs/04 §3) and resolved with the same-bar ambiguity policy.
        """
        if entry.stop_loss_price is None and entry.take_profit_price is None:
            return []
        children: list[Order] = []
        parent_id = entry.id

        if entry.stop_loss_price is not None:
            children.append(
                Order(
                    id=f"{parent_id}-sl",
                    symbol=entry.symbol,
                    direction=entry.direction,
                    order_type="stop",
                    shares=entry.shares,
                    stop_price=entry.stop_loss_price,
                    status="open",
                    eligible_from_utc=bar.bar_end_utc,
                    parent_order_id=parent_id,
                    creation_sequence=self._next_seq(),
                )
            )
        if entry.take_profit_price is not None:
            children.append(
                Order(
                    id=f"{parent_id}-tp",
                    symbol=entry.symbol,
                    direction=entry.direction,
                    order_type="limit",
                    shares=entry.shares,
                    limit_price=entry.take_profit_price,
                    status="open",
                    eligible_from_utc=bar.bar_end_utc,
                    parent_order_id=parent_id,
                    creation_sequence=self._next_seq(),
                )
            )

        for child in children:
            self._orders[child.id] = child
            self._emit(child, "accepted", bar.bar_end_utc)

        return self._resolve_children_on_bar(children, bar)

    def _resolve_children_on_bar(self, children: list[Order], bar: Bar) -> list[Fill]:
        """Apply the same-bar ambiguity policy when both children can fill on ``bar``."""
        stop = next((c for c in children if c.order_type == "stop"), None)
        target = next((c for c in children if c.order_type == "limit"), None)

        stop_hit = self._child_touches(stop, bar)
        target_hit = self._child_touches(target, bar)

        if stop_hit and target_hit and stop is not None and target is not None:
            winner = self._resolve_ambiguity(stop, target, bar)
            if winner is None:
                self._cancel_ambiguous_children(children, bar)
                return []
            return [self._fill_child(winner, bar)]

        if stop_hit and stop is not None:
            return [self._fill_child(stop, bar)]
        if target_hit and target is not None:
            return [self._fill_child(target, bar)]
        return []

    def _fill_child(self, child: Order, bar: Bar) -> Fill:
        base = self._match_base_price(child, bar)
        if base is None:
            raise FillEngineError(f"child {child.id} unexpectedly unmatched")
        fill = self._make_fill(child, base, bar.bar_end_utc)
        self._record_fill(child, fill, bar)
        return fill

    def _cancel_sibling_children(self, filled_child: Order, bar: Bar) -> None:
        """Cancel the other protective child when one side of a bracket fills."""
        if filled_child.parent_order_id is None:
            return
        parent_id = filled_child.parent_order_id
        for order in list(self._orders.values()):
            if (
                order.parent_order_id == parent_id
                and order.id != filled_child.id
                and order.status == "open"
            ):
                cancelled = order.model_copy(
                    update={"status": "cancelled", "reason": "SIBLING_FILLED"}
                )
                self._orders[order.id] = cancelled
                self._emit(cancelled, "cancelled", bar.bar_end_utc)

    def _cancel_open_children_for_symbol(self, symbol: str, bar: Bar) -> None:
        """Cancel every still-open protective child for ``symbol`` after a forced close.

        A forced session-close fill flattens the position; any remaining
        stop/target children of the closed bracket would otherwise be able to
        fill later in the next session (broker books are not cleared between
        sessions). They are cancelled with ``FORCED_SESSION_CLOSE_PARENT`` so
        the run ledger stays internally consistent (NFR-004).
        """
        for order in list(self._orders.values()):
            if (
                order.status == "open"
                and order.symbol == symbol
                and order.parent_order_id is not None
            ):
                cancelled = order.model_copy(
                    update={"status": "cancelled", "reason": "FORCED_SESSION_CLOSE_PARENT"}
                )
                self._orders[order.id] = cancelled
                self._emit(cancelled, "cancelled", bar.bar_end_utc)

    def _child_touches(self, child: Order | None, bar: Bar) -> bool:
        if child is None or child.status != "open":
            return False
        return self._match_base_price(child, bar) is not None

    def _resolve_ambiguity(self, stop: Order, target: Order, bar: Bar) -> Order | None:
        """Choose which protective child fills when both are reachable in the same bar."""
        policy = self._same_bar_policy
        if policy == "stop_first":
            return stop
        if policy == "target_first":
            return target
        if policy == "nearest_to_open":
            stop_dist = abs(bar.open - (stop.stop_price or bar.open))
            target_dist = abs(bar.open - (target.limit_price or bar.open))
            return stop if stop_dist <= target_dist else target
        if policy == "reject_ambiguous_bar":
            return None
        raise FillEngineError(f"unknown same-bar policy: {policy}")

    def _cancel_ambiguous_children(self, children: list[Order], bar: Bar) -> None:
        reason = "AMBIGUOUS_BAR_REJECTED"
        for child in children:
            if child.status == "open":
                cancelled = child.model_copy(update={"status": "cancelled", "reason": reason})
                self._orders[child.id] = cancelled
                self._emit(cancelled, "cancelled", bar.bar_end_utc)
        self._warnings.append(
            f"AMBIGUOUS_BAR_REJECTED at {bar.bar_end_utc.isoformat()} "
            f"symbol={bar.symbol}: protective children cancelled (policy={self._same_bar_policy})"
        )
