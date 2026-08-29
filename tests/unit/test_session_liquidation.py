"""T460 — Session-close liquidation tests.

Covers ``docs/04_BACKTEST_ENGINE.md`` §10 acceptance:

- normal-close forced liquidation at the final regular-session bar close;
- early-close days use the calendar-provided close (no hard-coded 16:00);
- forced exits are tagged ``FORCED_SESSION_CLOSE``;
- a strategy cannot exploit the final close to request a same-close fill
  (ADR-007; only the engine-generated forced close fills on that close);
- multi-symbol runs flatten every open symbol at its own final close;
- still-open protective children are cancelled after a forced close;
- ``force_flat_at_session_end=false`` disables the behavior.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import Field

from edgeback.config.models import (
    BacktestConfig,
    BaseStrictModel,
    CommissionConfig,
    DataConfig,
    DateRangeConfig,
    EngineConfig,
    ExecutionConfig,
    MarketConfig,
    ProjectConfig,
    ReportConfig,
    RiskConfig,
    RiskSizingConfig,
    SlippageConfig,
    SpreadConfig,
    StrategyConfig,
    VolumeParticipationConfig,
)
from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent
from edgeback.engine import run_multi_symbol_backtest, run_single_symbol_backtest
from edgeback.strategy.base import Strategy
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata

ET = ZoneInfo("America/New_York")


def make_bar(
    *,
    symbol: str = "AAA",
    session_date: date,
    hour: int,
    minute: int = 0,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 20_000,
) -> Bar:
    start_local = datetime(
        session_date.year, session_date.month, session_date.day, hour, minute, tzinfo=ET
    )
    start_utc = start_local.astimezone(UTC)
    end_utc = start_utc + timedelta(minutes=5)
    return Bar(
        symbol=symbol,
        provider_symbol=symbol,
        interval_seconds=300,
        bar_start_utc=start_utc,
        bar_end_utc=end_utc,
        session_date=session_date,
        session_type="regular",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_complete=True,
        source_provider="synthetic",
        source_feed="fixtures",
        adjustment_mode="split_adjusted",
        ingested_at_utc=end_utc,
    )


def make_config(
    symbol: str = "AAA",
    *,
    force_flat: bool = True,
    max_gross_exposure_pct: float = 100.0,
) -> BacktestConfig:
    return BacktestConfig(
        config_version="1.0",
        project=ProjectConfig(
            name="t460", tags=[], notes="session liquidation test", random_seed=42
        ),
        market=MarketConfig(calendar="XNYS", timezone="America/New_York", session="regular"),
        data=DataConfig(
            provider="synthetic",
            feed="fixtures",
            symbols=[symbol],
            interval="5m",
            date_range=DateRangeConfig(mode="rolling", lookback_calendar_days=5),
            adjustment_mode="split_adjusted",
            cache_dir="data",
            minimum_session_completeness_pct=98.0,
            missing_session_policy="fail_session",
            allow_incomplete_latest_bar=False,
        ),
        engine=EngineConfig(
            initial_cash_usd=100_000.0,
            signal_time="bar_close",
            market_fill_timing="next_bar_open",
            same_bar_bracket_policy="stop_first",
            force_flat_at_session_end=force_flat,
            entry_allocation="priority_then_symbol",
            fractional_shares=False,
            max_leverage=1.0,
        ),
        execution=ExecutionConfig(
            spread=SpreadConfig(model="fixed_bps", full_spread_bps=2.0),
            slippage=SlippageConfig(model="fixed_bps", bps_per_side=1.0),
            commission=CommissionConfig(model="per_share", usd_per_share=0.005),
            volume_participation=VolumeParticipationConfig(
                max_pct_of_bar_volume=30.0, on_exceed="reject"
            ),
        ),
        risk=RiskConfig(
            direction="both",
            sizing=RiskSizingConfig(model="fixed_shares", fixed_shares=100),
            max_position_pct_of_equity=50.0,
            max_gross_exposure_pct=max_gross_exposure_pct,
            max_concurrent_positions=10,
            max_trades_per_session=10,
            max_daily_loss_pct_of_starting_equity=100.0,
            max_consecutive_losses=100,
            entry_start_time="09:30",
            latest_entry_time="15:30",
            cooldown_bars_after_exit=0,
        ),
        strategy=StrategyConfig(name="test_holding", expected_version="0.1.0", params={}),
        report=ReportConfig(output_dir="runs", html=False),
    )


# ---------------------------------------------------------------------------
# Deterministic test strategies (injected; never registered globally)
# ---------------------------------------------------------------------------


class HoldingParams(BaseStrictModel):
    emit_on_bar_index: int = Field(1, ge=1)
    stop_offset: float | None = Field(default=None, gt=0.0)
    target_offset: float | None = Field(default=None, gt=0.0)


class HoldingStrategy(Strategy[HoldingParams]):
    """Enters a long position early in the session; never exits by itself."""

    strategy_id = "test_holding"
    strategy_version = "0.1.0"
    params_model = HoldingParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Holding",
            scope="per_symbol",
            warmup_bars=0,
        )

    def initialize(self, ctx: StrategyContext) -> None:
        self._bar_count = 0
        self._emitted = False

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        self._bar_count += 1
        if self._bar_count == self.params.emit_on_bar_index and not self._emitted:
            self._emitted = True
            kwargs: dict[str, object] = {
                "symbol": bar.symbol,
                "direction": "long",
                "intent_type": "market",
            }
            if self.params.stop_offset is not None and self.params.target_offset is not None:
                kwargs["stop_price"] = bar.close - self.params.stop_offset
                kwargs["take_profit_price"] = bar.close + self.params.target_offset
            return [ctx.create_intent(**kwargs)]
        return []


class FinalBarExitStrategy(HoldingStrategy):
    """Emits nothing beyond the early entry; never attempts a same-close exit."""

    strategy_id = "test_final_bar_exit"
    strategy_version = "0.1.0"
    params_model = HoldingParams


# ---------------------------------------------------------------------------
# 1. Normal-close forced liquidation (docs/04 §10)
# ---------------------------------------------------------------------------


def test_forced_liquidation_at_normal_close() -> None:
    """A position open at the final bar is liquidated at that close, tagged."""
    session = date(2025, 1, 13)  # Monday, regular 9:30-16:00 ET
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        # Signal at 09:35 close -> entry fills at 09:40 open.
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2
        ),
        make_bar(
            session_date=session, hour=9, minute=45, open_=100.2, high=100.6, low=100.0, close=100.4
        ),
        make_bar(
            session_date=session, hour=9, minute=50, open_=100.4, high=100.8, low=100.2, close=100.6
        ),
        make_bar(
            session_date=session,
            hour=15,
            minute=55,
            open_=100.6,
            high=100.9,
            low=100.4,
            close=100.7,
        ),
    ]
    result = run_single_symbol_backtest(
        make_config(),
        bars,
        strategy=HoldingStrategy(HoldingParams(emit_on_bar_index=2)),
    )
    assert result.status == "COMPLETED"
    # Entry fill + forced close fill.
    assert len(result.fills) == 2
    entry_fill = result.fills[0]
    close_fill = result.fills[1]
    assert entry_fill.reason != "FORCED_SESSION_CLOSE"
    assert close_fill.reason == "FORCED_SESSION_CLOSE"
    # Forced close fills at the final bar close (calendar close).
    assert close_fill.fill_price == bars[-1].close
    assert close_fill.timestamp_utc == bars[-1].bar_end_utc
    # Ledger is flat and reconciles.
    assert result.reconciliation is not None
    assert result.reconciliation.reconciled
    assert all("FORCED_SESSION_CLOSE" in w for w in result.warnings if "FORCED_SESSION_CLOSE" in w)
    assert any("FORCED_SESSION_CLOSE" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 2. Early-close uses calendar-provided close (docs/04 §10)
# ---------------------------------------------------------------------------


def test_forced_liquidation_at_early_close() -> None:
    """July 3rd early close: forced liquidation at 13:00 close, not 16:00."""
    session = date(2024, 7, 3)  # early close 13:00 ET
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        # Entry fills at 09:40 open.
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2
        ),
        # Last regular bar: 12:55-13:00.
        make_bar(
            session_date=session,
            hour=12,
            minute=55,
            open_=100.2,
            high=100.6,
            low=100.0,
            close=100.35,
        ),
    ]
    result = run_single_symbol_backtest(
        make_config(),
        bars,
        strategy=HoldingStrategy(HoldingParams(emit_on_bar_index=2)),
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 2
    close_fill = result.fills[1]
    assert close_fill.reason == "FORCED_SESSION_CLOSE"
    # The close is 13:00 ET, never 16:00.
    close_et = close_fill.timestamp_utc.astimezone(ET)
    assert close_et.hour == 13
    assert close_et.minute == 0
    assert close_fill.fill_price == bars[-1].close


# ---------------------------------------------------------------------------
# 3. No same-close exploit (ADR-007)
# ---------------------------------------------------------------------------


def test_strategy_cannot_exploit_final_close_for_same_close_fill() -> None:
    """A strategy intent emitted on the final close never fills at that close."""
    session = date(2025, 1, 13)
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        # Entry fills at 09:40 open.
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2
        ),
        # Final bar: strategy would like to exit at this close.
        make_bar(
            session_date=session,
            hour=15,
            minute=55,
            open_=100.2,
            high=100.8,
            low=100.0,
            close=100.7,
        ),
    ]
    result = run_single_symbol_backtest(
        make_config(),
        bars,
        strategy=FinalBarExitStrategy(HoldingParams(emit_on_bar_index=2)),
    )
    assert result.status == "COMPLETED"
    # Exactly two fills: the entry and one engine-generated forced close.
    assert len(result.fills) == 2
    assert result.fills[1].reason == "FORCED_SESSION_CLOSE"
    # The forced fill's timestamp equals the final bar end; no other fill is
    # placed there (a strategy-driven exit would have produced a 3rd fill).
    forced = result.fills[1]
    assert forced.timestamp_utc == bars[-1].bar_end_utc
    assert forced.fill_price == bars[-1].close


# ---------------------------------------------------------------------------
# 4. Protective children cancelled after forced close (NFR-004)
# ---------------------------------------------------------------------------


def test_protective_children_cancelled_after_forced_close() -> None:
    """Bracket children still open at the close are cancelled, not filled later."""
    session = date(2025, 1, 13)
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        # Entry fills at 09:40 open. The bar's range (99.8-100.2) stays inside
        # the stop 99.5 / target 101.0, so both children remain working.
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.2, low=99.8, close=100.1
        ),
        # Final bar range (100.0-100.6) also stays inside stop/target.
        make_bar(
            session_date=session,
            hour=15,
            minute=55,
            open_=100.2,
            high=100.6,
            low=100.0,
            close=100.5,
        ),
    ]
    result = run_single_symbol_backtest(
        make_config(),
        bars,
        strategy=HoldingStrategy(
            HoldingParams(emit_on_bar_index=2, stop_offset=0.5, target_offset=1.0)
        ),
    )
    assert result.status == "COMPLETED"
    # Entry + forced close.
    assert len(result.fills) == 2
    # The bracket's protective children were cancelled by the forced close.
    sl = next(o for o in result.orders if o.id.endswith("-sl"))
    tp = next(o for o in result.orders if o.id.endswith("-tp"))
    assert sl.status == "cancelled"
    assert sl.reason == "FORCED_SESSION_CLOSE_PARENT"
    assert tp.status == "cancelled"
    assert tp.reason == "FORCED_SESSION_CLOSE_PARENT"


# ---------------------------------------------------------------------------
# 5. force_flat_at_session_end=false disables forced close
# ---------------------------------------------------------------------------


def test_force_flat_disabled_keeps_position_open() -> None:
    """With force_flat_at_session_end=false no forced close occurs."""
    session = date(2025, 1, 13)
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2
        ),
    ]
    result = run_single_symbol_backtest(
        make_config(force_flat=False),
        bars,
        strategy=HoldingStrategy(HoldingParams(emit_on_bar_index=2)),
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 1
    assert result.fills[0].reason != "FORCED_SESSION_CLOSE"
    assert not any("FORCED_SESSION_CLOSE" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 6. Multi-symbol flat-at-close
# ---------------------------------------------------------------------------


def test_multi_symbol_liquidation_uses_each_symbols_own_final_close() -> None:
    """Each open symbol is liquidated at its own final-bar close."""
    session = date(2025, 1, 13)
    bars = [
        make_bar(
            symbol="AAA",
            session_date=session,
            hour=9,
            minute=30,
            open_=99.0,
            high=100.0,
            low=98.5,
            close=99.5,
        ),
        make_bar(
            symbol="BBB",
            session_date=session,
            hour=9,
            minute=30,
            open_=50.0,
            high=51.0,
            low=49.5,
            close=50.5,
        ),
        make_bar(
            symbol="AAA",
            session_date=session,
            hour=9,
            minute=35,
            open_=99.5,
            high=100.0,
            low=99.0,
            close=100.0,
        ),
        make_bar(
            symbol="BBB",
            session_date=session,
            hour=9,
            minute=35,
            open_=50.5,
            high=51.0,
            low=50.0,
            close=51.0,
        ),
        # Session-final timestamps for both symbols.
        make_bar(
            symbol="AAA",
            session_date=session,
            hour=15,
            minute=55,
            open_=100.0,
            high=100.5,
            low=99.8,
            close=100.3,
        ),
        make_bar(
            symbol="BBB",
            session_date=session,
            hour=15,
            minute=55,
            open_=51.0,
            high=51.6,
            low=50.9,
            close=51.4,
        ),
    ]

    def make_multi_config() -> BacktestConfig:
        config = make_config("AAA")
        return config.model_copy(
            update={
                "data": config.data.model_copy(update={"symbols": ["AAA", "BBB"]}),
                "strategy": StrategyConfig(
                    name="test_holding", expected_version="0.1.0", params={}
                ),
            }
        )

    strategies = {
        "AAA": HoldingStrategy(HoldingParams(emit_on_bar_index=2)),
        "BBB": HoldingStrategy(HoldingParams(emit_on_bar_index=2)),
    }
    result = run_multi_symbol_backtest(make_multi_config(), bars, strategies=strategies)
    assert result.status == "COMPLETED"
    # Entry per symbol + forced close per symbol = 4 fills.
    assert len(result.fills) == 4
    a_forced = next(
        f for f in result.fills if f.symbol == "AAA" and f.reason == "FORCED_SESSION_CLOSE"
    )
    b_forced = next(
        f for f in result.fills if f.symbol == "BBB" and f.reason == "FORCED_SESSION_CLOSE"
    )
    assert a_forced.fill_price == 100.3
    assert b_forced.fill_price == 51.4
    assert result.reconciliation is not None
    assert result.reconciliation.reconciled


# ---------------------------------------------------------------------------
# 7. Deterministic rerun includes forced close
# ---------------------------------------------------------------------------


def test_deterministic_rerun_with_forced_close() -> None:
    session = date(2025, 1, 13)
    bars = [
        make_bar(
            session_date=session, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5
        ),
        make_bar(
            session_date=session, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0
        ),
        make_bar(
            session_date=session, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2
        ),
        make_bar(
            session_date=session,
            hour=15,
            minute=55,
            open_=100.2,
            high=100.6,
            low=100.0,
            close=100.5,
        ),
    ]

    def run_once() -> object:
        return run_single_symbol_backtest(
            make_config(), bars, strategy=HoldingStrategy(HoldingParams(emit_on_bar_index=2))
        )

    first = run_once()
    second = run_once()
    assert first.fills == second.fills
    assert first.orders == second.orders
    assert first.broker_events == second.broker_events
    assert first.equity_curve == second.equity_curve
    assert first.warnings == second.warnings
