"""Tests for the T420 order lifecycle and fill engine (docs/08 §3 timing tests)."""

from datetime import UTC, datetime

import pytest

from edgeback.config.models import (
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    SpreadConfig,
    VolumeParticipationConfig,
)
from edgeback.domain.bars import Bar
from edgeback.domain.orders import Order
from edgeback.execution import (
    ExecutionCosts,
    FillEngineError,
    SimulatedBroker,
    build_execution_costs,
)


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2025, 1, 1, hour, minute, tzinfo=UTC)


def make_bar(
    *,
    symbol: str = "AAPL",
    start: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 10_000,
) -> Bar:
    end = start.replace(minute=start.minute + 5)
    return Bar(
        symbol=symbol,
        provider_symbol=symbol,
        interval_seconds=300,
        bar_start_utc=start,
        bar_end_utc=end,
        session_date=start.astimezone(UTC).date(),
        session_type="regular",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_complete=True,
        source_provider="fixture",
        source_feed="synthetic",
        adjustment_mode="raw",
        ingested_at_utc=end,
    )


def zero_costs() -> ExecutionCosts:
    return build_execution_costs(
        ExecutionConfig(
            spread=SpreadConfig(model="fixed_bps", full_spread_bps=0.0),
            slippage=SlippageConfig(model="fixed_bps", bps_per_side=0.0),
            commission=CommissionConfig(model="zero"),
            volume_participation=VolumeParticipationConfig(
                max_pct_of_bar_volume=1.0, on_exceed="reject"
            ),
        )
    )


def market_order(
    order_id: str,
    *,
    symbol: str = "AAPL",
    direction: str = "long",
    shares: int = 10,
    eligible_from: datetime,
    expires_at: datetime | None = None,
    priority: int = 0,
) -> Order:
    return Order(
        id=order_id,
        symbol=symbol,
        direction=direction,  # type: ignore[arg-type]
        order_type="market",
        shares=shares,
        status="pending",
        eligible_from_utc=eligible_from,
        expires_at_utc=expires_at,
        priority=priority,
    )


def bracket_order(
    order_id: str,
    *,
    symbol: str = "AAPL",
    direction: str = "long",
    shares: int = 10,
    eligible_from: datetime,
    stop_loss: float,
    take_profit: float,
) -> Order:
    return Order(
        id=order_id,
        symbol=symbol,
        direction=direction,  # type: ignore[arg-type]
        order_type="bracket",
        shares=shares,
        status="pending",
        eligible_from_utc=eligible_from,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
    )


# ---------------------------------------------------------------------------
# 1. No same-bar fill (docs/08 §3 #1)
# ---------------------------------------------------------------------------


def test_no_same_bar_fill_market_order() -> None:
    """A market order eligible from the next bar start must not fill on the signal bar."""
    broker = SimulatedBroker(zero_costs())
    # Signal produced at bar close 09:35 (end 09:35); eligibility = next bar start 09:35.
    broker.submit(
        market_order("o1", eligible_from=dt(9, 35)),
        now_utc=dt(9, 35),
    )

    signal_bar = make_bar(start=dt(9, 30), open_=100.0, high=105.0, low=99.0, close=104.0)
    fills = broker.on_bars([signal_bar])
    assert fills == []
    assert broker.get_order("o1") is not None
    assert broker.get_order("o1").status == "open"

    next_bar = make_bar(start=dt(9, 35), open_=106.0, high=107.0, low=105.5, close=106.5)
    fills = broker.on_bars([next_bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 106.0  # next bar open


# ---------------------------------------------------------------------------
# 2. Gap through stop (docs/08 §3 #4)
# ---------------------------------------------------------------------------


def test_gap_through_stop_fills_at_open() -> None:
    """A long protective stop gaps below when the bar opens below the stop; fill at open."""
    broker = SimulatedBroker(zero_costs())
    # Entry filled earlier; a long stop is a sell child order outside bracket path:
    # simulate a manual sell-stop protective order.
    stop = Order(
        id="long-sl",
        symbol="AAPL",
        direction="long",
        order_type="stop",
        shares=10,
        stop_price=100.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
        parent_order_id="entry",
    )
    broker.submit(stop, now_utc=dt(9, 35))

    # Bar opens at 98.0, below the 100 stop → gap through → base fill at open 98.0.
    bar = make_bar(start=dt(9, 35), open_=98.0, high=98.5, low=97.0, close=97.5)
    fills = broker.on_bars([bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 98.0
    assert broker.get_order("long-sl").status == "filled"


def test_stop_touch_fills_at_stop() -> None:
    """When the stop is merely touched (not gap-through), base fill is the stop price."""
    broker = SimulatedBroker(zero_costs())
    stop = Order(
        id="long-sl",
        symbol="AAPL",
        direction="long",
        order_type="stop",
        shares=10,
        stop_price=100.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
        parent_order_id="entry",
    )
    broker.submit(stop, now_utc=dt(9, 35))
    # Open 101 above the stop, low touches 99.5 → stop fill at 100.0.
    bar = make_bar(start=dt(9, 35), open_=101.0, high=101.5, low=99.5, close=99.8)
    fills = broker.on_bars([bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 100.0


# ---------------------------------------------------------------------------
# 3. Limit improvement (docs/04 §4)
# ---------------------------------------------------------------------------


def test_buy_limit_open_improvement() -> None:
    """Buy limit fills at open when open is at/below the limit."""
    broker = SimulatedBroker(zero_costs())
    limit = Order(
        id="buy-limit",
        symbol="AAPL",
        direction="long",
        order_type="limit",
        shares=10,
        limit_price=101.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
    )
    broker.submit(limit, now_utc=dt(9, 35))
    bar = make_bar(start=dt(9, 35), open_=100.5, high=102.0, low=100.0, close=101.5)
    fills = broker.on_bars([bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 100.5  # better of open/limit


def test_buy_limit_touch_fills_at_limit() -> None:
    """Buy limit whose low touches the limit fills at the limit price."""
    broker = SimulatedBroker(zero_costs())
    limit = Order(
        id="buy-limit",
        symbol="AAPL",
        direction="long",
        order_type="limit",
        shares=10,
        limit_price=100.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
    )
    broker.submit(limit, now_utc=dt(9, 35))
    # Open above limit, low touches 100.0 → fill at limit.
    bar = make_bar(start=dt(9, 35), open_=101.0, high=102.0, low=100.0, close=101.0)
    fills = broker.on_bars([bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 100.0


def test_sell_limit_open_improvement() -> None:
    """Sell limit fills at open when open is at/above the limit (closing a long)."""
    broker = SimulatedBroker(zero_costs())
    limit = Order(
        id="sell-limit",
        symbol="AAPL",
        direction="long",
        order_type="limit",
        shares=10,
        limit_price=99.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
        parent_order_id="entry",
    )
    broker.submit(limit, now_utc=dt(9, 35))
    bar = make_bar(start=dt(9, 35), open_=100.0, high=101.0, low=98.5, close=99.0)
    fills = broker.on_bars([bar])
    assert len(fills) == 1
    assert fills[0].fill_price == 100.0


# ---------------------------------------------------------------------------
# 4. Both stop and target touched (docs/08 §3 #5)
# ---------------------------------------------------------------------------


def _ambiguous_bracket_bars() -> list[Bar]:
    """Entry at 09:35 open=100; same bar low touches stop 99.0 and high touches target 103.0."""
    return [
        make_bar(start=dt(9, 30), open_=100.0, high=100.5, low=99.5, close=100.0),
        make_bar(start=dt(9, 35), open_=100.0, high=103.2, low=98.8, close=101.0),
    ]


def test_ambiguity_stop_first_within_entry_bar() -> None:
    broker = SimulatedBroker(zero_costs(), same_bar_policy="stop_first")
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    fills = broker.on_bars(_ambiguous_bracket_bars())
    assert len(fills) == 2  # entry + one protective child
    assert fills[0].order_id == "entry"
    assert fills[1].order_id == "entry-sl"
    # Stop merely touched (open 100 > stop 99, low 98.8) → base fill at stop 99.0.
    assert fills[1].fill_price == 99.0
    # Sibling target must be cancelled so it cannot fill later.
    assert broker.get_order("entry-tp").status == "cancelled"
    assert broker.get_order("entry-tp").reason == "SIBLING_FILLED"


def test_ambiguity_target_first_within_entry_bar() -> None:
    broker = SimulatedBroker(zero_costs(), same_bar_policy="target_first")
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    fills = broker.on_bars(_ambiguous_bracket_bars())
    assert len(fills) == 2
    assert fills[1].order_id == "entry-tp"
    assert fills[1].fill_price == 103.0  # limit target filled at limit
    assert broker.get_order("entry-sl").status == "cancelled"


def test_ambiguity_nearest_to_open() -> None:
    broker = SimulatedBroker(zero_costs(), same_bar_policy="nearest_to_open")
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    fills = broker.on_bars(_ambiguous_bracket_bars())
    # open=100: distance to stop 1.0 < distance to target 3.0 → stop wins.
    assert fills[1].order_id == "entry-sl"
    assert broker.get_order("entry-tp").status == "cancelled"


def test_ambiguity_reject_ambiguous_bar() -> None:
    broker = SimulatedBroker(zero_costs(), same_bar_policy="reject_ambiguous_bar")
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    fills = broker.on_bars(_ambiguous_bracket_bars())
    assert len(fills) == 1  # entry only; protective children rejected
    assert broker.get_order("entry-sl").status == "cancelled"
    assert broker.get_order("entry-sl").reason == "AMBIGUOUS_BAR_REJECTED"
    assert broker.get_order("entry-tp").status == "cancelled"
    assert any("AMBIGUOUS_BAR_REJECTED" in w for w in broker.warnings)


def test_invalid_same_bar_policy_rejected() -> None:
    with pytest.raises(ValueError, match="unknown same-bar policy"):
        SimulatedBroker(zero_costs(), same_bar_policy="bogus")


# ---------------------------------------------------------------------------
# 5. Bracket activation survives into later bars (no ambiguity)
# ---------------------------------------------------------------------------


def test_bracket_target_later_bar() -> None:
    broker = SimulatedBroker(zero_costs())
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    # Entry bar 09:35 open=100; no child touched that bar (range 99.5-100.5).
    entry_bar = make_bar(start=dt(9, 35), open_=100.0, high=100.5, low=99.5, close=100.2)
    fills_entry = broker.on_bars([entry_bar])
    assert len(fills_entry) == 1
    assert fills_entry[0].order_id == "entry"
    assert broker.get_order("entry-sl").status == "open"
    assert broker.get_order("entry-tp").status == "open"

    # Later bar touches target at 103 → target fills; stop sibling cancelled.
    target_bar = make_bar(start=dt(9, 40), open_=102.0, high=103.1, low=101.5, close=103.0)
    fills_target = broker.on_bars([target_bar])
    assert len(fills_target) == 1
    assert fills_target[0].order_id == "entry-tp"
    assert fills_target[0].fill_price == 103.0
    assert broker.get_order("entry-sl").status == "cancelled"
    assert broker.get_order("entry-sl").reason == "SIBLING_FILLED"


def test_bracket_stop_later_bar_gap() -> None:
    broker = SimulatedBroker(zero_costs())
    broker.submit(
        bracket_order("entry", eligible_from=dt(9, 35), stop_loss=99.0, take_profit=103.0),
        now_utc=dt(9, 35),
    )
    entry_bar = make_bar(start=dt(9, 35), open_=100.0, high=100.5, low=99.5, close=100.2)
    broker.on_bars([entry_bar])

    # Later bar gaps open 98 (< stop 99) → stop fills at open 98.0.
    stop_bar = make_bar(start=dt(9, 40), open_=98.0, high=98.4, low=97.6, close=97.8)
    fills = broker.on_bars([stop_bar])
    assert len(fills) == 1
    assert fills[0].order_id == "entry-sl"
    assert fills[0].fill_price == 98.0
    assert broker.get_order("entry-tp").status == "cancelled"


# ---------------------------------------------------------------------------
# 6. Expiry: missing next bar (docs/08 §3 #8)
# ---------------------------------------------------------------------------


def test_unfilled_order_expires_after_missing_bar() -> None:
    """A limit that never touches expires when a later bar starts past its expiry."""
    broker = SimulatedBroker(zero_costs())
    limit = Order(
        id="o2",
        symbol="AAPL",
        direction="long",
        order_type="limit",
        shares=10,
        limit_price=90.0,
        status="pending",
        eligible_from_utc=dt(9, 35),
        expires_at_utc=dt(9, 45),
    )
    broker.submit(limit, now_utc=dt(9, 35))
    # Bars at 09:35 and 09:40 never touch the 90 limit.
    broker.on_bars([make_bar(start=dt(9, 35), open_=100.0, high=101.0, low=99.5, close=100.5)])
    broker.on_bars([make_bar(start=dt(9, 40), open_=100.5, high=101.5, low=100.0, close=101.0)])
    assert broker.get_order("o2").status == "open"

    # Next delivered bar starts at 09:50 (> expiry 09:45): the order expires.
    broker.on_bars([make_bar(start=dt(9, 50), open_=102.0, high=103.0, low=101.5, close=102.5)])
    assert broker.get_order("o2").status == "cancelled"
    assert broker.get_order("o2").reason == "ORDER_EXPIRED"


# ---------------------------------------------------------------------------
# 7. Deterministic ordering (docs/02 §7, docs/04 §12)
# ---------------------------------------------------------------------------


def test_deterministic_order_evaluation() -> None:
    broker = SimulatedBroker(zero_costs())
    # Two market orders, same eligibility, different symbols/priorities.
    broker.submit(
        market_order("o-zz", symbol="ZZZZ", eligible_from=dt(9, 35), priority=0),
        now_utc=dt(9, 35),
    )
    broker.submit(
        market_order("o-aa", symbol="AAAA", eligible_from=dt(9, 35), priority=10),
        now_utc=dt(9, 35),
    )
    broker.submit(
        market_order("o-aa2", symbol="AAAA", eligible_from=dt(9, 35), priority=10),
        now_utc=dt(9, 35),
    )
    # Same timestamp, one bar per symbol (ADR-013 symbol filter).
    bars = [
        make_bar(symbol="AAAA", start=dt(9, 35), open_=100.0, high=101.0, low=99.5, close=100.5),
        make_bar(symbol="ZZZZ", start=dt(9, 35), open_=50.0, high=51.0, low=49.5, close=50.5),
    ]
    fills = broker.on_bars(bars)
    # Per symbol, sort by (-priority, symbol, creation_sequence):
    #   AAAA: o-aa (prio 10), o-aa2 (prio 10, later seq); ZZZZ: o-zz (prio 0).
    # on_bars processes AAAA first (sorted by bar_end_utc, equal → input order).
    assert [f.order_id for f in fills] == ["o-aa", "o-aa2", "o-zz"]
    assert fills[2].symbol == "ZZZZ"


def test_broker_symbol_filter_prevents_cross_symbol_fill() -> None:
    """An order for one symbol never matches another symbol's bar (ADR-013)."""
    broker = SimulatedBroker(zero_costs())
    broker.submit(market_order("aaa-order", symbol="AAAA", eligible_from=dt(9, 35)))
    # A BBB bar at the same time must not fill the AAAA order, even when the
    # price path would match.
    other_bar = make_bar(symbol="BBBB", start=dt(9, 35), open_=1.0, high=2.0, low=0.5, close=1.5)
    assert broker.on_bars([other_bar]) == []
    assert broker.get_order("aaa-order").status == "open"
    # The AAAA bar at the same timestamp fills it.
    own_bar = make_bar(
        symbol="AAAA", start=dt(9, 35), open_=100.0, high=101.0, low=99.5, close=100.5
    )
    fills = broker.on_bars([own_bar])
    assert len(fills) == 1
    assert fills[0].order_id == "aaa-order"


def test_broker_clock_rejects_backwards() -> None:
    broker = SimulatedBroker(zero_costs())
    broker.on_bars([make_bar(start=dt(9, 35), open_=100.0, high=101.0, low=99.0, close=100.0)])
    with pytest.raises(FillEngineError, match="moves backwards"):
        broker.on_bars([make_bar(start=dt(9, 30), open_=100.0, high=101.0, low=99.0, close=100.0)])


# ---------------------------------------------------------------------------
# 8. Lifecycle guards and cancellation
# ---------------------------------------------------------------------------


def test_submit_requires_pending_and_eligibility() -> None:
    broker = SimulatedBroker(zero_costs())
    with pytest.raises(FillEngineError, match="must declare eligible_from_utc"):
        broker.submit(Order(id="x", symbol="AAPL", direction="long", order_type="market", shares=1))
    already_open = Order(
        id="y",
        symbol="AAPL",
        direction="long",
        order_type="market",
        shares=1,
        status="open",
        eligible_from_utc=dt(9, 35),
    )
    with pytest.raises(FillEngineError, match="must be pending"):
        broker.submit(already_open)


def test_duplicate_submit_rejected() -> None:
    broker = SimulatedBroker(zero_costs())
    broker.submit(market_order("o1", eligible_from=dt(9, 35)))
    with pytest.raises(FillEngineError, match="already exists"):
        broker.submit(market_order("o1", eligible_from=dt(9, 35)))


def test_cancel_open_order_and_reject_filled() -> None:
    broker = SimulatedBroker(zero_costs())
    broker.submit(market_order("o1", eligible_from=dt(9, 35)))
    cancelled = broker.cancel("o1", now_utc=dt(9, 35), reason="MANUAL")
    assert cancelled.status == "cancelled"
    assert cancelled.reason == "MANUAL"
    with pytest.raises(FillEngineError, match="not open"):
        broker.cancel("o1", now_utc=dt(9, 36), reason="MANUAL")


def test_fill_carries_cost_decomposition() -> None:
    costs = build_execution_costs(
        ExecutionConfig(
            spread=SpreadConfig(model="fixed_bps", full_spread_bps=2.0),
            slippage=SlippageConfig(model="fixed_bps", bps_per_side=1.0),
            commission=CommissionConfig(model="per_share", usd_per_share=0.005),
            volume_participation=VolumeParticipationConfig(
                max_pct_of_bar_volume=1.0, on_exceed="reject"
            ),
        )
    )
    broker = SimulatedBroker(costs)
    broker.submit(market_order("o1", shares=100, eligible_from=dt(9, 35)))
    bar = make_bar(start=dt(9, 35), open_=100.0, high=101.0, low=99.5, close=100.5)
    fills = broker.on_bars([bar])
    fill = fills[0]
    # Half-spread 1 bps = 1.00; slippage 1 bps = 1.00; commission 100*0.005 = 0.50.
    assert fill.spread_usd == 1.0
    assert fill.slippage_usd == 1.0
    assert fill.commission_usd == 0.5
    assert fill.fill_price == 100.0
