from __future__ import annotations

from pathlib import Path

from edgeback.config import resolve_config
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.domain import RunStatus
from edgeback.engine import run_backtest

ROOT = Path(__file__).parents[2]


def test_multisymbol_engine_is_deterministic_and_next_bar_causal() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA", "BBB"])
    bars = generate_fixture_bars(symbols=("AAA", "BBB"), session_count=3)
    first = run_backtest(config, bars)
    second = run_backtest(config, bars)
    assert first.status is RunStatus.COMPLETED
    assert second.status is RunStatus.COMPLETED
    assert [trade.model_dump(mode="json") for trade in first.trades] == [
        trade.model_dump(mode="json") for trade in second.trades
    ]
    assert [fill.model_dump(mode="json") for fill in first.fills] == [
        fill.model_dump(mode="json") for fill in second.fills
    ]
    assert len(first.trades) == 4
    signal_by_intent = {intent.intent_id: intent.signal_time_utc for intent in first.intents}
    order_by_id = {order.order_id: order for order in first.orders}
    for fill in first.fills:
        order = order_by_id[fill.order_id]
        if order.intent_id is not None and order.parent_order_id is None:
            assert fill.timestamp_utc >= signal_by_intent[order.intent_id]
            # Same timestamp is the next bar's open, never the signal bar's close execution.
            assert fill.reason_code == "MARKET_NEXT_BAR_OPEN"
    assert first.reconciliation["reconciled"] is True


def test_force_flat_closes_open_positions_and_is_tagged() -> None:
    config = resolve_config(
        ROOT / "configs/example_backtest.yaml",
        symbols=["AAA"],
        params=["reward_risk=10.0"],
    )
    bars = generate_fixture_bars(symbols=("AAA",), session_count=2)
    result = run_backtest(config, bars)
    assert result.status is RunStatus.COMPLETED
    assert result.final_snapshot is not None
    assert result.final_snapshot.positions == ()
    assert any(fill.reason_code == "FORCED_SESSION_CLOSE" for fill in result.fills)


def test_engine_failure_retains_diagnostics() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = list(generate_fixture_bars(symbols=("AAA",), session_count=1))
    bars.reverse()
    result = run_backtest(config, bars)
    assert result.status is RunStatus.FAILED
    assert result.error_type == "SimulationError"
    assert result.traceback_text


def test_research_trade_window_uses_prior_sessions_only_as_warmup() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = generate_fixture_bars(symbols=("AAA",), session_count=3)
    allowed = {bars[-1].session_date}
    result = run_backtest(config, bars, trade_session_dates=allowed)
    assert result.status is RunStatus.COMPLETED
    assert all(trade.session_date in allowed for trade in result.trades)
    assert any(warning.code == "RESEARCH_WARMUP_INTENT_SUPPRESSED" for warning in result.warnings)
