from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edgeback.domain import (
    Bar,
    Fill,
    IdAllocator,
    Order,
    OrderEvent,
    OrderStatus,
    OrderType,
    Position,
    Side,
    WarningEvent,
)
from edgeback.execution.costs import ExecutionCosts


@dataclass(frozen=True, slots=True)
class BrokerResult:
    fills: tuple[Fill, ...] = ()
    events: tuple[OrderEvent, ...] = ()
    warnings: tuple[WarningEvent, ...] = ()


class SimulatedBroker:
    def __init__(
        self,
        costs: ExecutionCosts,
        ids: IdAllocator,
        *,
        same_bar_policy: str = "stop_first",
    ) -> None:
        self.costs = costs
        self.ids = ids
        self.same_bar_policy = same_bar_policy
        self._orders: dict[int, Order] = {}
        self._events: list[OrderEvent] = []
        self._warnings: list[WarningEvent] = []

    @property
    def orders(self) -> tuple[Order, ...]:
        return tuple(self._orders[key] for key in sorted(self._orders))

    @property
    def events(self) -> tuple[OrderEvent, ...]:
        return tuple(self._events)

    def order(self, order_id: int) -> Order:
        return self._orders[order_id]

    @property
    def warnings(self) -> tuple[WarningEvent, ...]:
        return tuple(self._warnings)

    def open_order_symbols(self) -> tuple[str, ...]:
        symbols = {
            order.symbol
            for order in self._orders.values()
            if order.status in {OrderStatus.CREATED, OrderStatus.ACCEPTED, OrderStatus.WORKING}
            and not order.reduce_only
        }
        return tuple(sorted(symbols))

    def submit(self, orders: tuple[Order, ...] | list[Order]) -> tuple[OrderEvent, ...]:
        emitted: list[OrderEvent] = []
        for order in sorted(orders, key=lambda item: (-item.priority, item.symbol, item.creation_sequence)):
            if order.order_id in self._orders:
                raise ValueError(f"Duplicate order id {order.order_id}")
            self._orders[order.order_id] = order
            if order.parent_order_id is None:
                emitted.append(self._transition(order.order_id, OrderStatus.WORKING, "SUBMITTED"))
            else:
                emitted.append(
                    self._record_event(order, None, OrderStatus.CREATED, "AWAITING_PARENT_FILL")
                )
        return tuple(emitted)


    def evaluate_bars(self, bars: tuple[Bar, ...] | list[Bar]) -> BrokerResult:
        """Evaluate a same-timestamp bar batch with globally chronological IDs.

        Per-symbol evaluation can discover an intrabar touch at ``bar_end`` before
        another symbol's next-open execution at ``bar_start``.  This adapter keeps
        the broker's deterministic symbol traversal while normalizing the events
        emitted by the whole timestamp batch into chronological order.
        """
        ordered_bars = sorted(bars, key=lambda item: item.symbol)
        if not ordered_bars:
            return BrokerResult()
        end_times = {bar.bar_end_utc for bar in ordered_bars}
        if len(end_times) != 1:
            raise ValueError("evaluate_bars requires bars with one common end timestamp")
        start_event_count = len(self._events)
        start_warning_count = len(self._warnings)
        discovered_fills: list[Fill] = []
        for bar in ordered_bars:
            discovered_fills.extend(self.evaluate_bar(bar).fills)

        fill_ids = sorted(fill.fill_id for fill in discovered_fills)
        sorted_fills = sorted(
            discovered_fills,
            key=lambda fill: (
                fill.timestamp_utc,
                -self._orders[fill.order_id].priority,
                fill.symbol,
                self._orders[fill.order_id].creation_sequence,
                fill.fill_id,
            ),
        )
        normalized_fills = tuple(
            fill.model_copy(update={"fill_id": fill_id})
            for fill, fill_id in zip(sorted_fills, fill_ids, strict=True)
        )

        new_events = self._events[start_event_count:]
        event_ids = sorted(event.event_id for event in new_events)
        sorted_events = sorted(
            new_events,
            key=lambda event: (
                event.timestamp_utc,
                -self._orders[event.order_id].priority,
                self._orders[event.order_id].symbol,
                self._orders[event.order_id].creation_sequence,
                event.event_id,
            ),
        )
        normalized_events = [
            event.model_copy(update={"event_id": event_id})
            for event, event_id in zip(sorted_events, event_ids, strict=True)
        ]
        self._events[start_event_count:] = normalized_events

        new_warnings = self._warnings[start_warning_count:]
        warning_ids = sorted(warning.warning_id for warning in new_warnings)
        sorted_warnings = sorted(
            new_warnings,
            key=lambda warning: (
                warning.timestamp_utc,
                warning.symbol or "",
                warning.code,
                warning.warning_id,
            ),
        )
        normalized_warnings = [
            warning.model_copy(update={"warning_id": warning_id})
            for warning, warning_id in zip(sorted_warnings, warning_ids, strict=True)
        ]
        self._warnings[start_warning_count:] = normalized_warnings
        return BrokerResult(
            fills=normalized_fills,
            events=tuple(normalized_events),
            warnings=tuple(normalized_warnings),
        )

    def evaluate_bar(self, bar: Bar) -> BrokerResult:
        start_event_count = len(self._events)
        start_warning_count = len(self._warnings)
        fills: list[Fill] = []
        self._expire_orders(bar)

        # Existing protective groups are resolved as a group before other orders.
        processed: set[int] = set()
        parent_ids = sorted(
            {
                order.parent_order_id
                for order in self._orders.values()
                if order.symbol == bar.symbol
                and order.parent_order_id is not None
                and order.status is OrderStatus.WORKING
            }
        )
        for parent_id in parent_ids:
            if parent_id is None:
                continue
            group = [
                order
                for order in self._orders.values()
                if order.parent_order_id == parent_id and order.status is OrderStatus.WORKING
            ]
            group_fill = self._evaluate_protective_group(group, bar)
            processed.update(order.order_id for order in group)
            if group_fill is not None:
                fills.append(group_fill)

        eligible = [
            order
            for order in self._orders.values()
            if order.symbol == bar.symbol
            and order.order_id not in processed
            and order.status is OrderStatus.WORKING
            and order.parent_order_id is None
            and order.eligible_from_utc <= bar.bar_start_utc
        ]
        eligible.sort(key=lambda item: (-item.priority, item.symbol, item.creation_sequence))
        for order in eligible:
            execution = self._execution(order, bar)
            if execution is None:
                continue
            base_price, timestamp, reason = execution
            fill = self._fill(order, base_price, timestamp, reason)
            fills.append(fill)
            children = self._activate_children(order.order_id, bar.bar_start_utc)
            if children:
                protective_fill = self._evaluate_protective_group(children, bar)
                if protective_fill is not None:
                    fills.append(protective_fill)

        return BrokerResult(
            fills=tuple(fills),
            events=tuple(self._events[start_event_count:]),
            warnings=tuple(self._warnings[start_warning_count:]),
        )

    def _expire_orders(self, bar: Bar) -> None:
        for order in list(self._orders.values()):
            if (
                order.symbol == bar.symbol
                and order.status in {OrderStatus.CREATED, OrderStatus.WORKING}
                and order.expires_at_utc is not None
                and bar.bar_start_utc >= order.expires_at_utc
            ):
                self._transition(
                    order.order_id,
                    OrderStatus.EXPIRED,
                    "DAY_ORDER_EXPIRED",
                    timestamp=bar.bar_start_utc,
                )
                self._cancel_children(order.order_id, bar.bar_start_utc, "PARENT_EXPIRED")

    def _execution(
        self, order: Order, bar: Bar
    ) -> tuple[float, datetime, str] | None:
        if order.eligible_from_utc > bar.bar_start_utc:
            return None
        if order.order_type is OrderType.MARKET:
            return bar.open, bar.bar_start_utc, "MARKET_NEXT_BAR_OPEN"
        if order.order_type is OrderType.LIMIT:
            assert order.limit_price is not None
            if order.side is Side.BUY:
                if bar.open <= order.limit_price:
                    return bar.open, bar.bar_start_utc, "LIMIT_OPEN_IMPROVEMENT"
                if bar.low <= order.limit_price:
                    return order.limit_price, bar.bar_end_utc, "LIMIT_TOUCHED"
            else:
                if bar.open >= order.limit_price:
                    return bar.open, bar.bar_start_utc, "LIMIT_OPEN_IMPROVEMENT"
                if bar.high >= order.limit_price:
                    return order.limit_price, bar.bar_end_utc, "LIMIT_TOUCHED"
            return None
        if order.order_type is OrderType.STOP:
            assert order.stop_price is not None
            if order.side is Side.BUY:
                if bar.open >= order.stop_price:
                    return bar.open, bar.bar_start_utc, "STOP_GAP_THROUGH"
                if bar.high >= order.stop_price:
                    return order.stop_price, bar.bar_end_utc, "STOP_TOUCHED"
            else:
                if bar.open <= order.stop_price:
                    return bar.open, bar.bar_start_utc, "STOP_GAP_THROUGH"
                if bar.low <= order.stop_price:
                    return order.stop_price, bar.bar_end_utc, "STOP_TOUCHED"
            return None
        return None

    def _evaluate_protective_group(self, group: list[Order], bar: Bar) -> Fill | None:
        if not group:
            return None
        active = [
            order
            for order in group
            if order.status is OrderStatus.WORKING and order.eligible_from_utc <= bar.bar_start_utc
        ]
        if not active:
            return None
        stop = next((order for order in active if order.order_type is OrderType.STOP), None)
        target = next((order for order in active if order.order_type is OrderType.LIMIT), None)
        stop_execution = self._execution(stop, bar) if stop is not None else None
        target_execution = self._execution(target, bar) if target is not None else None
        selected: Order | None = None
        execution: tuple[float, datetime, str] | None = None
        if stop_execution is not None and target_execution is not None:
            if self.same_bar_policy == "stop_first":
                selected, execution = stop, stop_execution
            elif self.same_bar_policy == "target_first":
                selected, execution = target, target_execution
            elif self.same_bar_policy == "nearest_to_open":
                assert stop is not None and target is not None
                stop_price = stop.stop_price or stop_execution[0]
                target_price = target.limit_price or target_execution[0]
                if abs(bar.open - stop_price) <= abs(bar.open - target_price):
                    selected, execution = stop, stop_execution
                else:
                    selected, execution = target, target_execution
            elif self.same_bar_policy == "reject_ambiguous_bar":
                assert stop is not None
                selected = stop
                execution = (bar.open, bar.bar_end_utc, "AMBIGUOUS_BAR_FORCED_EXIT")
                self._warnings.append(
                    WarningEvent(
                        warning_id=self.ids.next_warning(),
                        timestamp_utc=bar.bar_end_utc,
                        code="AMBIGUOUS_STOP_TARGET",
                        message="Both stop and target were reachable; trade was closed diagnostically.",
                        symbol=bar.symbol,
                        context={"parent_order_id": stop.parent_order_id},
                    )
                )
            else:
                raise ValueError(f"Unknown same-bar policy: {self.same_bar_policy}")
        elif stop_execution is not None:
            selected, execution = stop, stop_execution
        elif target_execution is not None:
            selected, execution = target, target_execution
        if selected is None or execution is None:
            return None
        fill = self._fill(selected, execution[0], execution[1], execution[2])
        self._cancel_siblings(selected, execution[1], "OCO_SIBLING_CANCELED")
        return fill

    def _fill(self, order: Order, base_price: float, timestamp: datetime, reason: str) -> Fill:
        decomposition = self.costs.decompose(
            base_price,
            order.quantity,
            order.side,
            limit_price=order.limit_price if order.order_type is OrderType.LIMIT else None,
        )
        fill = Fill(
            fill_id=self.ids.next_fill(),
            order_id=order.order_id,
            intent_id=order.intent_id,
            parent_order_id=order.parent_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            timestamp_utc=timestamp,
            base_price=decomposition.base_price,
            spread_cost_usd=decomposition.spread_cost_usd,
            slippage_cost_usd=decomposition.slippage_cost_usd,
            commission_usd=decomposition.commission_usd,
            effective_price=decomposition.effective_price,
            reason_code=reason,
            model_ids=decomposition.model_ids,
            tags=order.tags,
        )
        self._transition(order.order_id, OrderStatus.FILLED, reason, timestamp=timestamp)
        return fill

    def _activate_children(self, parent_order_id: int, timestamp: datetime) -> list[Order]:
        activated: list[Order] = []
        for order in list(self._orders.values()):
            if order.parent_order_id == parent_order_id and order.status is OrderStatus.CREATED:
                self._transition(
                    order.order_id,
                    OrderStatus.WORKING,
                    "PARENT_FILLED",
                    timestamp=timestamp,
                )
                activated.append(self._orders[order.order_id])
        return activated

    def _cancel_siblings(self, selected: Order, timestamp: datetime, reason: str) -> None:
        for order in list(self._orders.values()):
            if (
                order.parent_order_id == selected.parent_order_id
                and order.order_id != selected.order_id
                and order.status in {OrderStatus.CREATED, OrderStatus.WORKING}
            ):
                self._transition(order.order_id, OrderStatus.CANCELED, reason, timestamp=timestamp)

    def _cancel_children(self, parent_id: int, timestamp: datetime, reason: str) -> None:
        for order in list(self._orders.values()):
            if order.parent_order_id == parent_id and order.status in {
                OrderStatus.CREATED,
                OrderStatus.WORKING,
            }:
                self._transition(order.order_id, OrderStatus.CANCELED, reason, timestamp=timestamp)

    def cancel_session_orders(
        self, timestamp: datetime, *, symbol: str | None = None
    ) -> tuple[OrderEvent, ...]:
        start_event_count = len(self._events)
        for order in list(self._orders.values()):
            if (
                (symbol is None or order.symbol == symbol)
                and order.status in {OrderStatus.CREATED, OrderStatus.WORKING}
            ):
                self._transition(order.order_id, OrderStatus.CANCELED, "SESSION_END", timestamp=timestamp)
        return tuple(self._events[start_event_count:])

    def force_flat(self, positions: tuple[Position, ...], final_bars: dict[str, Bar]) -> BrokerResult:
        start_event_count = len(self._events)
        fills: list[Fill] = []
        for position in sorted(positions, key=lambda item: item.symbol):
            if position.quantity == 0 or position.symbol not in final_bars:
                continue
            bar = final_bars[position.symbol]
            side = Side.SELL if position.quantity > 0 else Side.BUY
            order_id = self.ids.next_order()
            order = Order(
                order_id=order_id,
                intent_id=None,
                strategy_id="__engine__",
                strategy_version="0.1.0",
                symbol=position.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=abs(position.quantity),
                status=OrderStatus.WORKING,
                created_at_utc=bar.bar_end_utc,
                eligible_from_utc=bar.bar_end_utc,
                expires_at_utc=bar.bar_end_utc,
                priority=10_000,
                creation_sequence=order_id,
                reduce_only=True,
                reason_code="FORCED_SESSION_CLOSE",
                tags=("forced", "session_close"),
            )
            self._orders[order_id] = order
            self._record_event(order, None, OrderStatus.WORKING, "FORCED_SESSION_CLOSE")
            fills.append(
                self._fill(
                    order,
                    bar.close,
                    bar.bar_end_utc,
                    "FORCED_SESSION_CLOSE",
                )
            )
            self.cancel_session_orders(bar.bar_end_utc, symbol=position.symbol)
        return BrokerResult(fills=tuple(fills), events=tuple(self._events[start_event_count:]))

    def _transition(
        self,
        order_id: int,
        status: OrderStatus,
        reason: str,
        *,
        timestamp: datetime | None = None,
    ) -> OrderEvent:
        current = self._orders[order_id]
        previous = current.status
        payload = current.model_dump(mode="python")
        payload["status"] = status
        updated = Order.model_validate(payload)
        self._orders[order_id] = updated
        return self._record_event(
            updated,
            previous,
            status,
            reason,
            timestamp=timestamp,
        )

    def _record_event(
        self,
        order: Order,
        previous: OrderStatus | None,
        status: OrderStatus,
        reason: str,
        *,
        timestamp: datetime | None = None,
    ) -> OrderEvent:
        event = OrderEvent(
            event_id=self.ids.next_event(),
            order_id=order.order_id,
            timestamp_utc=timestamp or order.created_at_utc,
            previous_status=previous,
            status=status,
            reason_code=reason,
        )
        self._events.append(event)
        return event
