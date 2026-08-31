from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgeback.config import resolve_config
from edgeback.domain import Fill, IdAllocator, Side
from edgeback.execution import ExecutionCosts
from edgeback.portfolio import PortfolioLedger

ROOT = Path(__file__).parents[2]


def test_cost_decomposition_is_adverse_and_limit_capped() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml")
    costs = ExecutionCosts(config.execution)
    buy = costs.decompose(100.0, 100, Side.BUY)
    sell = costs.decompose(100.0, 100, Side.SELL)
    assert buy.effective_price > 100
    assert sell.effective_price < 100
    assert buy.commission_usd == pytest.approx(0.5)
    capped = costs.decompose(100.0, 100, Side.BUY, limit_price=100.005)
    assert capped.effective_price <= 100.005 + 1e-12


def test_portfolio_long_short_round_trips_reconcile_costs() -> None:
    ids = IdAllocator()
    ledger = PortfolioLedger(100_000, ids)
    t0 = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
    fills = [
        Fill(
            fill_id=1,
            order_id=1,
            symbol="AAA",
            side=Side.BUY,
            quantity=10,
            timestamp_utc=t0,
            base_price=100,
            spread_cost_usd=0.1,
            slippage_cost_usd=0.1,
            commission_usd=0.1,
            effective_price=100.02,
            reason_code="ENTRY",
        ),
        Fill(
            fill_id=2,
            order_id=2,
            symbol="AAA",
            side=Side.SELL,
            quantity=10,
            timestamp_utc=t0.replace(minute=35),
            base_price=101,
            spread_cost_usd=0.1,
            slippage_cost_usd=0.1,
            commission_usd=0.1,
            effective_price=100.98,
            reason_code="EXIT",
        ),
        Fill(
            fill_id=3,
            order_id=3,
            symbol="BBB",
            side=Side.SELL,
            quantity=5,
            timestamp_utc=t0.replace(minute=40),
            base_price=50,
            spread_cost_usd=0.05,
            slippage_cost_usd=0.05,
            commission_usd=0.05,
            effective_price=49.98,
            reason_code="ENTRY",
        ),
        Fill(
            fill_id=4,
            order_id=4,
            symbol="BBB",
            side=Side.BUY,
            quantity=5,
            timestamp_utc=t0.replace(minute=45),
            base_price=49,
            spread_cost_usd=0.05,
            slippage_cost_usd=0.05,
            commission_usd=0.05,
            effective_price=49.02,
            reason_code="EXIT",
        ),
    ]
    for fill in fills:
        ledger.apply_fill(fill)
    assert len(ledger.trades) == 2
    assert sum(trade.gross_pnl_usd for trade in ledger.trades) == pytest.approx(15.0)
    assert ledger.quantity("AAA") == 0
    assert ledger.quantity("BBB") == 0
    assert ledger.reconcile()["reconciled"] is True


def test_ledger_rejects_fill_that_exceeds_max_leverage_without_mutation() -> None:
    from edgeback.errors import SimulationError

    ids = IdAllocator()
    ledger = PortfolioLedger(1_000, ids, max_leverage=1.0)
    before = ledger.snapshot(datetime(2025, 1, 6, 14, 30, tzinfo=UTC))
    fill = Fill(
        fill_id=1,
        order_id=1,
        symbol="AAA",
        side=Side.BUY,
        quantity=20,
        timestamp_utc=datetime(2025, 1, 6, 14, 30, tzinfo=UTC),
        base_price=100,
        spread_cost_usd=0,
        slippage_cost_usd=0,
        commission_usd=0,
        effective_price=100,
        reason_code="OVERLEVERED",
    )
    with pytest.raises(SimulationError):
        ledger.apply_fill(fill)
    after = ledger.snapshot(datetime(2025, 1, 6, 14, 30, tzinfo=UTC))
    assert before.cash_usd == after.cash_usd
    assert not ledger.fills
