from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from edgeback.config import resolve_config
from edgeback.domain import Bar, IdAllocator, Order, OrderStatus, OrderType, Side
from edgeback.execution import ExecutionCosts, SimulatedBroker

ROOT = Path(__file__).parents[2]


def bar(start: datetime, *, open_: float = 100, high: float = 102, low: float = 98, close: float = 101) -> Bar:
    return Bar(
        symbol="AAA",
        provider_symbol="AAA",
        interval_seconds=300,
        bar_start_utc=start,
        bar_end_utc=start + timedelta(minutes=5),
        session_date=start.date(),
        session_type="regular",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100_000,
        source_provider="fixture",
        source_feed="fixture",
        adjustment_mode="raw",
        ingested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def order(ids: IdAllocator, created: datetime, **updates: object) -> Order:
    order_id = ids.next_order()
    payload = {
        "order_id": order_id,
        "strategy_id": "test",
        "strategy_version": "0.1.0",
        "symbol": "AAA",
        "side": Side.BUY,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "status": OrderStatus.ACCEPTED,
        "created_at_utc": created,
        "eligible_from_utc": created,
        "expires_at_utc": created + timedelta(hours=6),
        "priority": 0,
        "creation_sequence": order_id,
    }
    payload.update(updates)
    return Order.model_validate(payload)


def test_market_signal_cannot_fill_signal_bar_and_fills_next_open() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    ids = IdAllocator()
    broker = SimulatedBroker(ExecutionCosts(config.execution), ids)
    signal_end = datetime(2025, 1, 6, 14, 35, tzinfo=UTC)
    broker.submit([order(ids, signal_end)])
    prior = bar(datetime(2025, 1, 6, 14, 30, tzinfo=UTC))
    assert not broker.evaluate_bar(prior).fills
    next_bar = bar(signal_end, open_=101, high=102, low=100, close=101.5)
    fills = broker.evaluate_bar(next_bar).fills
    assert fills[0].base_price == 101
    assert fills[0].timestamp_utc == signal_end


def test_limit_improvement_and_gap_through_stop() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    ids = IdAllocator()
    broker = SimulatedBroker(ExecutionCosts(config.execution), ids)
    start = datetime(2025, 1, 6, 14, 35, tzinfo=UTC)
    broker.submit(
        [
            order(ids, start, order_type=OrderType.LIMIT, limit_price=100.0),
            order(ids, start, side=Side.SELL, order_type=OrderType.STOP, stop_price=99.0),
        ]
    )
    fills = broker.evaluate_bar(bar(start, open_=98.0, high=100.5, low=97.0, close=99.0)).fills
    assert fills[0].base_price == 98.0
    assert fills[1].base_price == 98.0
    assert fills[1].reason_code == "STOP_GAP_THROUGH"


def test_same_bar_bracket_policy_is_explicit() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    start = datetime(2025, 1, 6, 14, 35, tzinfo=UTC)
    for policy, expected_tag in (("stop_first", "stop"), ("target_first", "target")):
        ids = IdAllocator()
        broker = SimulatedBroker(ExecutionCosts(config.execution), ids, same_bar_policy=policy)
        parent = order(ids, start)
        stop = order(
            ids,
            start,
            parent_order_id=parent.order_id,
            status=OrderStatus.CREATED,
            side=Side.SELL,
            order_type=OrderType.STOP,
            stop_price=99.0,
            reduce_only=True,
            tags=("protective", "stop"),
        )
        target = order(
            ids,
            start,
            parent_order_id=parent.order_id,
            status=OrderStatus.CREATED,
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            limit_price=101.0,
            reduce_only=True,
            tags=("protective", "target"),
        )
        broker.submit([parent, stop, target])
        fills = broker.evaluate_bar(bar(start, open_=100, high=102, low=98, close=100)).fills
        assert len(fills) == 2
        assert expected_tag in fills[1].tags


def test_nearest_and_reject_ambiguous_policies_are_deterministic() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    start = datetime(2026, 1, 6, 14, 35, tzinfo=UTC)

    ids = IdAllocator()
    nearest = SimulatedBroker(ExecutionCosts(config.execution), ids, same_bar_policy="nearest_to_open")
    parent = order(ids, start)
    stop = order(
        ids,
        start,
        parent_order_id=parent.order_id,
        status=OrderStatus.CREATED,
        side=Side.SELL,
        order_type=OrderType.STOP,
        stop_price=99.0,
        reduce_only=True,
        tags=("protective", "stop"),
    )
    target = order(
        ids,
        start,
        parent_order_id=parent.order_id,
        status=OrderStatus.CREATED,
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        limit_price=103.0,
        reduce_only=True,
        tags=("protective", "target"),
    )
    nearest.submit([parent, stop, target])
    nearest_result = nearest.evaluate_bar(bar(start, open_=100, high=104, low=98, close=101))
    assert "stop" in nearest_result.fills[-1].tags

    ids = IdAllocator()
    rejected = SimulatedBroker(
        ExecutionCosts(config.execution),
        ids,
        same_bar_policy="reject_ambiguous_bar",
    )
    parent = order(ids, start)
    stop = order(
        ids,
        start,
        parent_order_id=parent.order_id,
        status=OrderStatus.CREATED,
        side=Side.SELL,
        order_type=OrderType.STOP,
        stop_price=99.0,
        reduce_only=True,
        tags=("protective", "stop"),
    )
    target = order(
        ids,
        start,
        parent_order_id=parent.order_id,
        status=OrderStatus.CREATED,
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        limit_price=101.0,
        reduce_only=True,
        tags=("protective", "target"),
    )
    rejected.submit([parent, stop, target])
    rejected_result = rejected.evaluate_bar(bar(start, open_=100, high=102, low=98, close=100))
    assert rejected_result.fills[-1].reason_code == "AMBIGUOUS_BAR_FORCED_EXIT"
    assert rejected_result.fills[-1].timestamp_utc == start + timedelta(minutes=5)
    assert rejected_result.warnings[-1].code == "AMBIGUOUS_STOP_TARGET"


def test_missing_next_bar_order_expires_without_backfill() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    ids = IdAllocator()
    broker = SimulatedBroker(ExecutionCosts(config.execution), ids)
    signal_end = datetime(2026, 1, 6, 20, 55, tzinfo=UTC)
    pending = order(
        ids,
        signal_end,
        eligible_from_utc=signal_end,
        expires_at_utc=signal_end + timedelta(minutes=5),
    )
    broker.submit([pending])

    # There is no eligible bar at 20:55.  The next observed bar begins only
    # after expiry, so the order must expire rather than being backfilled.
    later = bar(signal_end + timedelta(minutes=5), open_=110, high=111, low=109, close=110)
    result = broker.evaluate_bar(later)
    assert not result.fills
    assert broker.order(pending.order_id).status is OrderStatus.EXPIRED
    assert result.events[-1].reason_code == "DAY_ORDER_EXPIRED"


def test_early_close_forced_liquidation_uses_calendar_final_close() -> None:
    from edgeback.calendar import XNYSCalendar
    from edgeback.domain import Position

    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    calendar = XNYSCalendar()
    session = calendar.session(date(2026, 11, 27))
    assert session.is_early_close
    final_start = session.close_utc - timedelta(minutes=5)
    final_bar = bar(final_start, open_=101, high=102, low=100, close=101.25)

    ids = IdAllocator()
    broker = SimulatedBroker(ExecutionCosts(config.execution), ids)
    result = broker.force_flat(
        (Position(symbol="AAA", quantity=7, average_price=100, last_price=101.25),),
        {"AAA": final_bar},
    )
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.timestamp_utc == session.close_utc
    assert fill.base_price == final_bar.close
    assert fill.reason_code == "FORCED_SESSION_CLOSE"
    assert fill.side is Side.SELL
