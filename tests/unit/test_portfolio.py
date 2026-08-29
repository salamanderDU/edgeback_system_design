"""Tests for the T400 portfolio ledger and accounting invariants."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from edgeback.domain.fills import Fill
from edgeback.domain.positions import PortfolioSnapshot, Position
from edgeback.portfolio import (
    AccountingError,
    PortfolioLedger,
    cash_delta_for_fill,
    effective_price,
    project_fills,
    round_money,
    signed_quantity,
    total_fill_cost_usd,
    weighted_average,
)


def dt(hour: int = 9, minute: int = 30) -> datetime:
    return datetime(2025, 1, 1, hour, minute, tzinfo=UTC)


def make_fill(
    *,
    fill_id: str,
    order_id: str,
    symbol: str,
    action: str,
    shares: int,
    price: float,
    ts: datetime,
    commission: float = 0.0,
    spread: float = 0.0,
    slippage: float = 0.0,
) -> Fill:
    return Fill(
        id=fill_id,
        order_id=order_id,
        symbol=symbol,
        timestamp_utc=ts,
        direction="long" if action == "buy" else "short",
        action=action,
        shares=shares,
        fill_price=price,
        commission_usd=commission,
        slippage_usd=slippage,
        spread_usd=spread,
    )


# ---------------------------------------------------------------------------
# Pure accounting helpers
# ---------------------------------------------------------------------------


def test_round_money_half_up() -> None:
    assert round_money(1.005) == 1.01
    assert round_money(1.004) == 1.0
    assert round_money(-1.005) == -1.01


def test_signed_quantity_and_cash_delta() -> None:
    buy = make_fill(
        fill_id="f1",
        order_id="o1",
        symbol="AAPL",
        action="buy",
        shares=10,
        price=100.0,
        ts=dt(),
        commission=2.0,
        spread=1.0,
        slippage=0.5,
    )
    sell = make_fill(
        fill_id="f2",
        order_id="o2",
        symbol="AAPL",
        action="sell",
        shares=10,
        price=110.0,
        ts=dt(10),
    )
    assert signed_quantity(buy) == 10
    assert signed_quantity(sell) == -10
    assert total_fill_cost_usd(buy) == 3.5
    # Buy: -(10 * 100) - 3.5
    assert cash_delta_for_fill(buy) == -1003.5
    # Sell: +(10 * 110) - 0
    assert cash_delta_for_fill(sell) == 1100.0


def test_effective_price_adverse_with_commission() -> None:
    buy = make_fill(
        fill_id="f1",
        order_id="o1",
        symbol="AAPL",
        action="buy",
        shares=10,
        price=100.0,
        ts=dt(),
        spread=1.0,
        slippage=0.5,
        commission=2.0,
    )
    sell = make_fill(
        fill_id="f2",
        order_id="o2",
        symbol="AAPL",
        action="sell",
        shares=10,
        price=110.0,
        ts=dt(10),
        spread=1.0,
        slippage=0.5,
        commission=2.0,
    )
    # Informational effective price includes adverse spread/slippage AND commission:
    # buy 100 + (1 + 0.5 + 2)/10 = 100.35; sell 110 - 0.35 = 109.65.
    assert effective_price(buy) == 100.35
    assert effective_price(sell) == 109.65


def test_weighted_average() -> None:
    assert weighted_average(0, 0.0, 100, 50.0) == 50.0
    assert weighted_average(100, 50.0, 100, 70.0) == 60.0
    # (100*50 + 3*70) / 103 = 5210 / 103 ≈ 50.5825
    assert round(weighted_average(100, 50.0, 3, 70.0), 4) == 50.5825


# ---------------------------------------------------------------------------
# Ledger long accounting
# ---------------------------------------------------------------------------


def test_long_round_trip_with_costs() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(),
            commission=5.0,
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="sell",
            shares=100,
            price=110.0,
            ts=dt(10),
            commission=5.0,
        ),
        order_id=2,
    )

    assert ledger.cash == round_money(100_000.0 - 10_000.0 - 5.0 + 11_000.0 - 5.0)
    assert ledger.is_flat()
    # Realized P&L uses base prices: 100 * (110 - 100) = 1000. Commissions are
    # separate cash costs.
    assert ledger.realized_pnl == 1000.0
    assert ledger.total_commission_usd == 10.0
    assert ledger.applied_fill_count == 2
    assert ledger.position("AAPL").shares == 0

    rep = ledger.reconcile()
    assert rep.reconciled, rep.position_differences
    assert rep.cash_difference == 0.0
    assert rep.fill_count == 2


def test_long_weighted_average_partial_close() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(),
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=120.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    # Weighted average: (100*100 + 100*120)/200 = 110
    assert ledger.position("AAPL").shares == 200
    assert ledger.position("AAPL").average_price == 110.0

    ledger.apply_fill(
        make_fill(
            fill_id="f3",
            order_id="o3",
            symbol="AAPL",
            action="sell",
            shares=50,
            price=130.0,
            ts=dt(11),
        ),
        order_id=3,
    )
    # Realized: 50 * (130 - 110) = 1000
    assert ledger.realized_pnl == 1000.0
    assert ledger.position("AAPL").shares == 150
    assert ledger.position("AAPL").average_price == 110.0
    assert ledger.reconcile().reconciled


def test_long_flip_to_short() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(),
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="sell",
            shares=150,
            price=90.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    # Closed 100 @ 90 -> realized -1000; flipped 50 short @ 90.
    assert ledger.realized_pnl == -1000.0
    assert ledger.position("AAPL").shares == -50
    assert ledger.position("AAPL").average_price == 90.0
    assert ledger.reconcile().reconciled


# ---------------------------------------------------------------------------
# Ledger short accounting
# ---------------------------------------------------------------------------


def test_short_round_trip_with_costs() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="TSLA",
            action="sell",
            shares=100,
            price=200.0,
            ts=dt(),
            commission=5.0,
            spread=2.0,
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="TSLA",
            action="buy",
            shares=100,
            price=180.0,
            ts=dt(10),
            commission=5.0,
            spread=2.0,
        ),
        order_id=2,
    )

    assert ledger.position("TSLA").shares == 0
    # Realized P&L uses base prices: 100 * (200 - 180) = 2000. All spread,
    # slippage, and commission costs flow through cash separately.
    assert ledger.realized_pnl == 2000.0
    assert ledger.total_spread_usd == 4.0
    assert ledger.total_commission_usd == 10.0
    assert ledger.total_costs_usd == 14.0
    assert ledger.reconcile().reconciled


def test_short_weighted_average_cover() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="TSLA",
            action="sell",
            shares=100,
            price=200.0,
            ts=dt(),
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="TSLA",
            action="sell",
            shares=100,
            price=220.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    # Weighted average short: (100*200 + 100*220)/200 = 210
    assert ledger.position("TSLA").shares == -200
    assert ledger.position("TSLA").average_price == 210.0

    ledger.apply_fill(
        make_fill(
            fill_id="f3",
            order_id="o3",
            symbol="TSLA",
            action="buy",
            shares=50,
            price=190.0,
            ts=dt(11),
        ),
        order_id=3,
    )
    # Cover realized: 50 * (210 - 190) = 1000. Remaining short keeps avg 210.
    assert ledger.realized_pnl == 1000.0
    assert ledger.position("TSLA").shares == -150
    assert ledger.position("TSLA").average_price == 210.0
    assert ledger.reconcile().reconciled


def test_short_flip_to_long() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="TSLA",
            action="sell",
            shares=100,
            price=200.0,
            ts=dt(),
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="TSLA",
            action="buy",
            shares=150,
            price=210.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    # Covers 100 short at 210 -> realized -1000; flipped 50 long @ 210.
    assert ledger.realized_pnl == -1000.0
    assert ledger.position("TSLA").shares == 50
    assert ledger.position("TSLA").average_price == 210.0
    assert ledger.reconcile().reconciled


# ---------------------------------------------------------------------------
# Mark-to-market, exposure, and equity
# ---------------------------------------------------------------------------


def test_mark_to_market_and_equity_long() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(),
        ),
        order_id=1,
    )
    assert ledger.equity() == 100_000.0  # cash 90k + 100*100
    assert ledger.unrealized_pnl("AAPL") == 0.0

    ledger.mark_to_market("AAPL", 110.0)
    assert ledger.unrealized_pnl("AAPL") == 1000.0
    assert ledger.equity() == 101_000.0
    assert ledger.gross_exposure() == 11_000.0
    assert ledger.net_exposure() == 11_000.0

    snap: PortfolioSnapshot = ledger.snapshot()
    assert snap.cash == 90_000.0
    assert snap.equity == 101_000.0
    assert snap.gross_exposure == 11_000.0
    assert snap.net_exposure == 11_000.0
    assert ledger.reconcile().reconciled


def test_mark_to_market_short_equity() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="TSLA",
            action="sell",
            shares=100,
            price=200.0,
            ts=dt(),
        ),
        order_id=1,
    )
    assert ledger.equity() == 100_000.0  # cash 120k - 100*200
    ledger.mark_to_market("TSLA", 180.0)
    assert ledger.unrealized_pnl("TSLA") == 2000.0
    assert ledger.equity() == 102_000.0
    assert ledger.gross_exposure() == 18_000.0
    assert ledger.net_exposure() == -18_000.0


def test_leverage_guard_blocks_high_exposure() -> None:
    # Disable the cash guard so the leverage guard is exercised in isolation.
    ledger = PortfolioLedger(initial_cash=10_000.0, max_leverage=1.0, min_cash=None)
    # Buying 200 shares at 60 = 12,000 gross vs 10,000 equity.
    with pytest.raises(AccountingError, match="maximum leverage"):
        ledger.apply_fill(
            make_fill(
                fill_id="f1",
                order_id="o1",
                symbol="AAPL",
                action="buy",
                shares=200,
                price=60.0,
                ts=dt(),
            ),
            order_id=1,
        )
    # Ledger must be untouched after the rejected fill.
    assert ledger.is_flat()
    assert ledger.cash == 10_000.0
    assert ledger.applied_fill_count == 0

    # A compliant fill passes and running leverage stays within the limit.
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=60.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    assert ledger.position("AAPL").shares == 100
    assert ledger.leverage() <= 1.0 + 1e-9
    assert ledger.reconcile().reconciled


def test_cash_guard_rejects_and_leaves_state_untouched() -> None:
    ledger = PortfolioLedger(initial_cash=1_000.0, min_cash=0.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=10.0,
            ts=dt(),
        ),
        order_id=1,
    )
    assert ledger.cash == 0.0
    with pytest.raises(AccountingError, match="minimum cash"):
        ledger.apply_fill(
            make_fill(
                fill_id="f2",
                order_id="o2",
                symbol="AAPL",
                action="buy",
                shares=1,
                price=10.0,
                ts=dt(10),
            ),
            order_id=2,
        )
    assert ledger.cash == 0.0
    assert ledger.position("AAPL").shares == 100
    assert ledger.applied_fill_count == 1


# ---------------------------------------------------------------------------
# Guards: timezone, ordering, zero shares, mark validation
# ---------------------------------------------------------------------------


def test_naive_timestamp_rejected() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    naive = datetime(2025, 1, 1, 9, 30)  # no tzinfo
    with pytest.raises(AccountingError, match="timezone-aware"):
        ledger.apply_fill(
            make_fill(
                fill_id="f1",
                order_id="o1",
                symbol="AAPL",
                action="buy",
                shares=10,
                price=100.0,
                ts=naive,  # type: ignore[arg-type]
            ),
            order_id=1,
        )


def test_backwards_timestamp_rejected() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=10,
            price=100.0,
            ts=dt(10),
        ),
        order_id=1,
    )
    with pytest.raises(AccountingError, match="moves backwards"):
        ledger.apply_fill(
            make_fill(
                fill_id="f2",
                order_id="o2",
                symbol="AAPL",
                action="sell",
                shares=5,
                price=110.0,
                ts=dt(9),
            ),
            order_id=2,
        )


def test_order_id_guard() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=10,
            price=100.0,
            ts=dt(),
        ),
        order_id=2,
    )
    with pytest.raises(AccountingError, match="moves backwards"):
        ledger.apply_fill(
            make_fill(
                fill_id="f2",
                order_id="o2",
                symbol="AAPL",
                action="sell",
                shares=5,
                price=110.0,
                ts=dt(10),
            ),
            order_id=1,
        )


def test_zero_shares_rejected() -> None:
    # The domain Fill model already forbids non-positive shares, so a zero-share
    # fill can never be constructed; the ledger's guard is defense in depth.
    with pytest.raises(ValidationError):
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=0,
            price=100.0,
            ts=dt(),
        )


def test_invalid_constructor_args() -> None:
    with pytest.raises(ValueError, match="initial_cash"):
        PortfolioLedger(initial_cash=0.0)
    with pytest.raises(ValueError, match="max_leverage"):
        PortfolioLedger(initial_cash=100.0, max_leverage=0.0)
    with pytest.raises(ValueError, match="min_cash"):
        PortfolioLedger(initial_cash=100.0, min_cash=-1.0)


def test_mark_to_market_rejects_non_positive() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    with pytest.raises(ValueError, match="mark price"):
        ledger.mark_to_market("AAPL", 0.0)


# ---------------------------------------------------------------------------
# Reconciliation invariants
# ---------------------------------------------------------------------------


def test_reconcile_empty_ledger() -> None:
    ledger = PortfolioLedger(initial_cash=50_000.0)
    rep = ledger.reconcile()
    assert rep.reconciled
    assert rep.cash == 50_000.0
    assert rep.fill_count == 0
    assert rep.realized_pnl == 0.0


def test_reconcile_multi_symbol_mixed_history() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    fills = [
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(9),
            commission=3.0,
            spread=1.0,
        ),
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="sell",
            shares=40,
            price=112.0,
            ts=dt(10),
            slippage=2.0,
        ),
        make_fill(
            fill_id="f3",
            order_id="o3",
            symbol="MSFT",
            action="sell",
            shares=50,
            price=300.0,
            ts=dt(11),
            commission=5.0,
            spread=3.0,
            slippage=1.0,
        ),
        make_fill(
            fill_id="f4",
            order_id="o4",
            symbol="MSFT",
            action="buy",
            shares=20,
            price=295.0,
            ts=dt(12),
        ),
    ]
    for i, fill in enumerate(fills, start=1):
        ledger.apply_fill(fill, order_id=i)

    assert ledger.position("AAPL").shares == 60
    assert ledger.position("AAPL").average_price == 100.0
    assert ledger.position("MSFT").shares == -30
    # Sell 50 @ 300 then buy 20 @ 295 (no costs): 20 of 50 shorts are covered,
    # so the residual 30-share short keeps the original 300.0 average.
    assert ledger.position("MSFT").average_price == 300.0

    # Apply marks to reach an equity figure.
    ledger.mark_to_market("AAPL", 115.0)
    ledger.mark_to_market("MSFT", 298.0)

    rep = ledger.reconcile()
    assert rep.reconciled, rep.position_differences
    assert rep.cash_difference == 0.0
    assert rep.realized_pnl == ledger.realized_pnl
    # Equity = cash + signed marks.
    assert ledger.equity() == round_money(ledger.cash + 60 * 115.0 - 30 * 298.0)


def test_project_fills_matches_hand_computed_history() -> None:
    """The independent replay must match hand-computed cash, positions, and realized P&L."""
    fills = [
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="AAPL",
            action="buy",
            shares=100,
            price=100.0,
            ts=dt(9),
            commission=3.0,
            spread=1.0,
        ),
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="sell",
            shares=40,
            price=112.0,
            ts=dt(10),
            slippage=2.0,
        ),
        make_fill(
            fill_id="f3",
            order_id="o3",
            symbol="MSFT",
            action="sell",
            shares=50,
            price=300.0,
            ts=dt(11),
            commission=5.0,
            spread=3.0,
            slippage=1.0,
        ),
        make_fill(
            fill_id="f4",
            order_id="o4",
            symbol="MSFT",
            action="buy",
            shares=20,
            price=295.0,
            ts=dt(12),
        ),
    ]
    result = project_fills(initial_cash=100_000.0, fills=fills)

    # Cash: 100k - 100*100 - 3 - 1               (AAPL buy)
    #       + 40*112 - 2                          (AAPL partial sell)
    #       + 50*300 - 5 - 3 - 1                  (MSFT short open)
    #       - 20*295                              (MSFT partial cover)
    expected_cash = 100_000.0 - 10_000.0 - 3.0 - 1.0 + 4_480.0 - 2.0 + 15_000.0 - 9.0 - 5_900.0
    assert result.cash == round_money(expected_cash)

    # Realized P&L at base prices:
    # AAPL close 40: 40 * (112 - 100) = 480
    # MSFT cover 20: 20 * (300 - 295) = 100
    aapl_realized = round_money(40 * (112.0 - 100.0))
    msft_realized = round_money(20 * (300.0 - 295.0))
    assert result.realized_pnl == round_money(aapl_realized + msft_realized)

    assert result.positions["AAPL"].shares == 60
    assert result.positions["AAPL"].average_price == 100.0
    assert result.positions["MSFT"].shares == -30
    assert result.positions["MSFT"].average_price == 300.0
    assert result.total_commission_usd == 8.0
    assert result.total_spread_usd == 4.0
    assert result.total_slippage_usd == 3.0
    assert result.total_costs_usd == 15.0
    assert result.fill_count == 4


# ---------------------------------------------------------------------------
# Domain model position output
# ---------------------------------------------------------------------------


def test_positions_output_is_deterministic_and_typed() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    ledger.apply_fill(
        make_fill(
            fill_id="f1",
            order_id="o1",
            symbol="MSFT",
            action="buy",
            shares=10,
            price=300.0,
            ts=dt(9),
        ),
        order_id=1,
    )
    ledger.apply_fill(
        make_fill(
            fill_id="f2",
            order_id="o2",
            symbol="AAPL",
            action="buy",
            shares=5,
            price=100.0,
            ts=dt(10),
        ),
        order_id=2,
    )
    ledger.mark_to_market("AAPL", 110.0)
    ledger.mark_to_market("MSFT", 310.0)
    positions = ledger.positions()
    assert list(positions.keys()) == ["AAPL", "MSFT"]  # sorted by symbol
    aapl: Position = positions["AAPL"]
    assert aapl.shares == 5
    assert aapl.unrealized_pnl == 50.0
    msft: Position = positions["MSFT"]
    assert msft.unrealized_pnl == 100.0


def test_applied_fills_returns_copy() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    fill = make_fill(
        fill_id="f1",
        order_id="o1",
        symbol="AAPL",
        action="buy",
        shares=1,
        price=100.0,
        ts=dt(),
    )
    ledger.apply_fill(fill, order_id=1)
    snapshot = ledger.applied_fills()
    snapshot.clear()
    assert ledger.applied_fill_count == 1


def test_reconciliation_report_as_dict() -> None:
    ledger = PortfolioLedger(initial_cash=100_000.0)
    rep = ledger.reconcile()
    d = rep.as_dict()
    assert d["reconciled"] is True
    assert d["fill_count"] == 0
    assert d["position_differences"] == {}
