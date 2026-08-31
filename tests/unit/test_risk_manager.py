"""Tests for the T430 risk manager: sizing, limits, lockouts, and reason codes."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from edgeback.config.models import (
    RiskConfig,
    RiskSizingConfig,
    VolumeParticipationConfig,
)
from edgeback.domain.orders import OrderIntent
from edgeback.domain.positions import Position
from edgeback.risk import RiskContext, RiskManager, RiskReason, risk_manager_from_config


def dt_ny(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """A US/Eastern wall-clock time expressed in UTC (10:00 NY = 15:00 UTC in EST)."""
    # 2025-01-01 is US Eastern Standard Time (UTC-5), so UTC = local + 5.
    return datetime(2025, 1, day, hour + 5, minute, tzinfo=UTC)


def intent(
    *,
    symbol: str = "AAPL",
    direction: str = "long",
    intent_type: str = "market",
    stop_price: float | None = None,
    protective_exit: bool = False,
) -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        direction=direction,  # type: ignore[arg-type]
        intent_type=intent_type,  # type: ignore[arg-type]
        stop_price=stop_price,
        protective_exit=protective_exit,
    )


def risk_config(
    *,
    sizing: RiskSizingConfig | None = None,
    direction: str = "both",
    max_position_pct: float = 100.0,
    max_gross_pct: float = 100.0,
    max_concurrent: int = 5,
    max_trades: int = 10,
    max_daily_loss_pct: float = 1.0,
    max_consecutive_losses: int = 3,
    entry_start: str = "09:30",
    latest_entry: str = "15:30",
    cooldown_bars: int = 0,
) -> RiskConfig:
    return RiskConfig(
        direction=direction,  # type: ignore[arg-type]
        sizing=sizing
        or RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=0.25),
        max_position_pct_of_equity=max_position_pct,
        max_gross_exposure_pct=max_gross_pct,
        max_concurrent_positions=max_concurrent,
        max_trades_per_session=max_trades,
        max_daily_loss_pct_of_starting_equity=max_daily_loss_pct,
        max_consecutive_losses=max_consecutive_losses,
        entry_start_time=entry_start,
        latest_entry_time=latest_entry,
        cooldown_bars_after_exit=cooldown_bars,
    )


def ctx(
    *,
    equity: float = 100_000.0,
    cash: float = 100_000.0,
    positions: dict[str, Position] | None = None,
    gross: float = 0.0,
    reference: dict[str, float] | None = None,
    session_pnl: float = 0.0,
    ts_utc: datetime | None = None,
    bar_volume: int | None = None,
    estimated_cost_per_share: float = 0.0,
) -> RiskContext:
    return RiskContext(
        equity=equity,
        cash=cash,
        positions=positions or {},
        gross_exposure=gross,
        reference_prices=reference or {"AAPL": 100.0},
        session_pnl=session_pnl,
        current_time_utc=ts_utc or dt_ny(10, 0),
        session_date=date(2025, 1, 1),
        bar_volume=bar_volume,
        estimated_cost_per_share=estimated_cost_per_share,
    )


# ---------------------------------------------------------------------------
# Risk-per-trade sizing (docs/04 §8)
# ---------------------------------------------------------------------------


def test_risk_per_trade_sizing_formula() -> None:
    """shares = floor(equity * risk_pct / (|ref - stop| + cost_per_share))."""
    mgr = RiskManager(risk_config())
    # equity=100k, 0.25% -> budget 250; risk per share = |100-99| + 0 = 1 -> 250 shares.
    decision = mgr.evaluate(
        intent(stop_price=99.0),
        ctx(equity=100_000.0, reference={"AAPL": 100.0}, estimated_cost_per_share=0.0),
    )
    assert decision.accepted
    assert decision.reason == RiskReason.OK
    assert decision.sized_shares == 250
    assert decision.order is not None
    assert decision.order.shares == 250
    assert decision.order.stop_price == 99.0


def test_risk_per_trade_includes_estimated_cost() -> None:
    mgr = RiskManager(risk_config())
    # risk per share = 1.0 + 0.5 = 1.5 -> 250 / 1.5 = 166 shares.
    decision = mgr.evaluate(
        intent(stop_price=99.0),
        ctx(equity=100_000.0, reference={"AAPL": 100.0}, estimated_cost_per_share=0.5),
    )
    assert decision.accepted
    assert decision.sized_shares == 166


def test_risk_per_trade_requires_stop() -> None:
    mgr = RiskManager(risk_config())
    decision = mgr.evaluate(intent(), ctx())
    assert not decision.accepted
    assert decision.reason == RiskReason.INVALID_STOP


def test_risk_per_trade_zero_size_rejected() -> None:
    mgr = RiskManager(
        risk_config(
            sizing=RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=0.001)
        )
    )
    # budget = 100k * 0.001% = 1.0; risk per share = 100 - 50 = 50 -> 0 shares.
    decision = mgr.evaluate(
        intent(stop_price=50.0),
        ctx(equity=100_000.0, reference={"AAPL": 100.0}),
    )
    assert not decision.accepted
    assert decision.reason == RiskReason.SIZING_POSITIVE_SHARES_REQUIRED


# ---------------------------------------------------------------------------
# Other sizing modes
# ---------------------------------------------------------------------------


def test_fixed_shares_sizing() -> None:
    mgr = RiskManager(risk_config(sizing=RiskSizingConfig(model="fixed_shares", fixed_shares=100)))
    decision = mgr.evaluate(intent(), ctx())
    assert decision.accepted
    assert decision.sized_shares == 100


def test_fixed_notional_sizing() -> None:
    mgr = RiskManager(
        risk_config(sizing=RiskSizingConfig(model="fixed_notional", fixed_notional_usd=5_000.0))
    )
    # 5000 / 100 = 50 shares.
    decision = mgr.evaluate(intent(), ctx(reference={"AAPL": 100.0}))
    assert decision.accepted
    assert decision.sized_shares == 50


def test_percent_equity_sizing() -> None:
    mgr = RiskManager(
        risk_config(sizing=RiskSizingConfig(model="percent_equity", percent_equity_pct=10.0))
    )
    # 100k * 10% / 100 = 100 shares.
    decision = mgr.evaluate(intent(), ctx(equity=100_000.0, reference={"AAPL": 100.0}))
    assert decision.accepted
    assert decision.sized_shares == 100


def test_sizing_config_requires_params() -> None:
    with pytest.raises(ValidationError, match="fixed_notional sizing requires fixed_notional_usd"):
        RiskSizingConfig(model="fixed_notional")
    with pytest.raises(ValidationError, match="percent_equity sizing requires percent_equity_pct"):
        RiskSizingConfig(model="percent_equity")


# ---------------------------------------------------------------------------
# Direction and entry-time windows
# ---------------------------------------------------------------------------


def test_direction_forbidden() -> None:
    mgr = RiskManager(risk_config(direction="long"))
    decision = mgr.evaluate(intent(direction="short"), ctx())
    assert not decision.accepted
    assert decision.reason == RiskReason.DIRECTION_FORBIDDEN


def test_entry_window_rejects_outside_hours() -> None:
    mgr = RiskManager(risk_config(entry_start="09:30", latest_entry="15:30"))
    decision = mgr.evaluate(intent(), ctx(ts_utc=dt_ny(16, 0)))
    assert not decision.accepted
    assert decision.reason == RiskReason.ENTRY_WINDOW


def test_entry_window_accepts_inside_hours() -> None:
    mgr = RiskManager(risk_config(entry_start="09:30", latest_entry="15:30"))
    decision = mgr.evaluate(intent(stop_price=99.0), ctx(ts_utc=dt_ny(10, 0)))
    assert decision.accepted


# ---------------------------------------------------------------------------
# Caps: per-position, gross exposure, cash, participation
# ---------------------------------------------------------------------------


def test_per_position_cap_resizes() -> None:
    mgr = RiskManager(risk_config(max_position_pct=50.0))
    # Sized 250 by risk_per_trade; cap = 100k * 50% / 100 = 500 shares -> no resize.
    decision = mgr.evaluate(
        intent(stop_price=99.0), ctx(equity=100_000.0, reference={"AAPL": 100.0})
    )
    assert decision.accepted
    assert decision.sized_shares == 250

    # A cap whose share maximum floors to zero -> PER_POSITION_LIMIT.
    # 0.0005% of 100k = 0.50 USD -> 0 shares at 100.
    mgr2 = RiskManager(risk_config(max_position_pct=0.0005))
    decision2 = mgr2.evaluate(
        intent(stop_price=99.0), ctx(equity=100_000.0, reference={"AAPL": 100.0})
    )
    assert not decision2.accepted
    assert decision2.reason == RiskReason.PER_POSITION_LIMIT


def test_gross_exposure_cap() -> None:
    mgr = RiskManager(risk_config(max_gross_pct=50.0))
    # max_gross = 100k * 50% = 50k (derived by the manager from start equity).
    decision = mgr.evaluate(
        intent(stop_price=99.0),
        ctx(equity=100_000.0, gross=49_900.0, reference={"AAPL": 100.0}),
    )
    # Notional 250*100 = 25k; 49.9k + 25k = 74.9k > 50k -> rejected.
    assert not decision.accepted
    assert decision.reason == RiskReason.GROSS_EXPOSURE_LIMIT


def test_cash_limit() -> None:
    mgr = RiskManager(risk_config())
    decision = mgr.evaluate(intent(stop_price=99.0), ctx(cash=100.0, reference={"AAPL": 100.0}))
    assert not decision.accepted
    assert decision.reason == RiskReason.CASH_LIMIT


def test_volume_participation_reject() -> None:
    mgr = RiskManager(
        risk_config(),
        volume_participation=VolumeParticipationConfig(
            max_pct_of_bar_volume=1.0, on_exceed="reject"
        ),
    )
    # Sized 250; bar volume 100 -> cap 1 share -> reject.
    decision = mgr.evaluate(intent(stop_price=99.0), ctx(bar_volume=100, reference={"AAPL": 100.0}))
    assert not decision.accepted
    assert decision.reason == RiskReason.VOLUME_PARTICIPATION_EXCEEDED


def test_volume_participation_cap_resizes() -> None:
    mgr = RiskManager(
        risk_config(),
        volume_participation=VolumeParticipationConfig(max_pct_of_bar_volume=10.0, on_exceed="cap"),
    )
    # Cap 10% of 5000 = 500 -> no resize; use small volume to force cap.
    decision = mgr.evaluate(
        intent(stop_price=99.0),
        ctx(bar_volume=1_000, reference={"AAPL": 100.0}),
    )
    # cap = 10% * 1000 = 100 shares.
    assert decision.accepted
    assert decision.sized_shares == 100


# ---------------------------------------------------------------------------
# Daily lockouts, trade counts, cooldown, consecutive losses
# ---------------------------------------------------------------------------


def test_daily_loss_lockout() -> None:
    mgr = RiskManager(risk_config(max_daily_loss_pct=1.0))
    mgr.on_session_start(100_000.0)
    decision = mgr.evaluate(intent(stop_price=99.0), ctx(session_pnl=-1_000.0))
    assert not decision.accepted
    assert decision.reason == RiskReason.DAILY_LOSS_LOCKOUT


def test_max_trades_lockout() -> None:
    mgr = RiskManager(risk_config(max_trades=1))
    mgr.on_session_start(100_000.0)
    mgr.record_trade(realized_pnl=-10.0)  # first trade consumed
    decision = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert not decision.accepted
    assert decision.reason == RiskReason.MAX_TRADES_REACHED


def test_max_consecutive_losses_lockout() -> None:
    mgr = RiskManager(risk_config(max_consecutive_losses=2))
    mgr.on_session_start(100_000.0)
    mgr.record_trade(realized_pnl=-10.0)
    mgr.record_trade(realized_pnl=-20.0)
    decision = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert not decision.accepted
    assert decision.reason == RiskReason.MAX_CONSECUTIVE_LOSSES
    # A win resets the counter.
    mgr.record_trade(realized_pnl=+10.0)
    mgr2 = RiskManager(risk_config(max_consecutive_losses=2))
    mgr2.on_session_start(100_000.0)
    mgr2.record_trade(realized_pnl=-10.0)
    mgr2.record_trade(realized_pnl=+5.0)
    assert mgr2.evaluate(intent(stop_price=99.0), ctx()).accepted


def test_cooldown_blocks_immediate_reenry() -> None:
    mgr = RiskManager(risk_config(cooldown_bars=2))
    mgr.on_session_start(100_000.0)
    mgr.record_trade(realized_pnl=-10.0)
    mgr.on_bar()  # 1 bar since exit
    decision = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert not decision.accepted
    assert decision.reason == RiskReason.COOLDOWN_ACTIVE

    mgr.on_bar()  # 2 bars -> cooldown satisfied
    decision = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert decision.accepted


def test_duplicate_entry_rejected() -> None:
    mgr = RiskManager(risk_config())
    mgr.on_session_start(100_000.0)
    first = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert first.accepted
    second = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert not second.accepted
    assert second.reason == RiskReason.DUPLICATE_ORDER


def test_max_concurrent_positions() -> None:
    mgr = RiskManager(risk_config(max_concurrent=1))
    mgr.on_session_start(100_000.0)
    positions = {"AAPL": Position(symbol="AAPL", shares=100, average_price=100.0)}
    decision = mgr.evaluate(intent(stop_price=99.0), ctx(positions=positions))
    assert not decision.accepted
    assert decision.reason == RiskReason.MAX_POSITIONS_REACHED


# ---------------------------------------------------------------------------
# Protective exits bypass lockouts and sizing (docs/04 §9)
# ---------------------------------------------------------------------------


def test_protective_exit_bypasses_daily_loss_lockout() -> None:
    mgr = RiskManager(risk_config(max_daily_loss_pct=1.0))
    mgr.on_session_start(100_000.0)
    decision = mgr.evaluate(
        intent(protective_exit=True),
        ctx(session_pnl=-2_000.0),
    )
    assert decision.accepted
    assert decision.reason == RiskReason.OK


def test_protective_exit_bypasses_max_trades_and_size() -> None:
    mgr = RiskManager(risk_config(max_trades=1))
    mgr.on_session_start(100_000.0)
    mgr.record_trade(realized_pnl=-10.0)  # consumes the single trade allowance
    # A normal entry would now be rejected ...
    blocked = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert not blocked.accepted
    assert blocked.reason == RiskReason.MAX_TRADES_REACHED
    # ... but a protective exit passes through despite the lockout.
    decision = mgr.evaluate(intent(protective_exit=True), ctx())
    assert decision.accepted
    assert decision.order is None  # engine owns the exit order construction


# ---------------------------------------------------------------------------
# Factory & session lifecycle
# ---------------------------------------------------------------------------


def test_session_reset_clears_lockouts() -> None:
    mgr = RiskManager(risk_config(max_trades=1))
    mgr.on_session_start(100_000.0)
    mgr.record_trade(realized_pnl=-10.0)
    assert mgr.evaluate(intent(stop_price=99.0), ctx()).reason == RiskReason.MAX_TRADES_REACHED
    mgr.on_session_start(100_000.0)  # new session resets counters
    assert mgr.evaluate(intent(stop_price=99.0), ctx()).accepted


def test_manager_from_config_with_execution() -> None:
    config = risk_config()
    mgr = risk_manager_from_config(config)
    assert isinstance(mgr, RiskManager)
    decision = mgr.evaluate(intent(stop_price=99.0), ctx())
    assert decision.accepted


def test_missing_reference_price_rejected() -> None:
    mgr = RiskManager(risk_config())
    decision = mgr.evaluate(intent(symbol="ZZZZ"), ctx(reference={"AAPL": 100.0}))
    assert not decision.accepted
    assert decision.reason == RiskReason.SIZING_POSITIVE_SHARES_REQUIRED
