"""Tests for the T440 deterministic single-symbol event engine.

Covers docs/08 §3 mandatory timing tests (no same-bar fill, future mutation,
warmup isolation), docs/04 §2-3 §13 exact event sequence, NFR-001 deterministic
rerun, and docs/02 §9 failure diagnostics retention.
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
from edgeback.engine import EngineRunResult, SingleSymbolEventEngine, run_single_symbol_backtest
from edgeback.strategy.base import Strategy
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata

SESSION_DATE = date(2025, 1, 13)
ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def local_utc(hour: int, minute: int = 0) -> datetime:
    """2025-01-13 local ET converted to UTC (EST = UTC-5)."""
    return datetime(2025, 1, 13, hour, minute, tzinfo=ET).astimezone(UTC)


def make_bar(
    *,
    symbol: str = "AAA",
    hour: int,
    minute: int = 0,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 10_000,
) -> Bar:
    start_utc = local_utc(hour, minute)
    end_utc = start_utc + timedelta(minutes=5)
    return Bar(
        symbol=symbol,
        provider_symbol=symbol,
        interval_seconds=300,
        bar_start_utc=start_utc,
        bar_end_utc=end_utc,
        session_date=SESSION_DATE,
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


def make_config(symbol: str = "AAA") -> BacktestConfig:
    return BacktestConfig(
        config_version="1.0",
        project=ProjectConfig(name="t440", tags=[], notes="engine test", random_seed=42),
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
            force_flat_at_session_end=True,
            entry_allocation="priority_then_symbol",
            fractional_shares=False,
            max_leverage=1.0,
        ),
        execution=ExecutionConfig(
            spread=SpreadConfig(model="fixed_bps", full_spread_bps=2.0),
            slippage=SlippageConfig(model="fixed_bps", bps_per_side=1.0),
            commission=CommissionConfig(model="per_share", usd_per_share=0.005),
            volume_participation=VolumeParticipationConfig(
                max_pct_of_bar_volume=10.0, on_exceed="reject"
            ),
        ),
        risk=RiskConfig(
            direction="both",
            sizing=RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=0.25),
            max_position_pct_of_equity=25.0,
            max_gross_exposure_pct=100.0,
            max_concurrent_positions=3,
            max_trades_per_session=4,
            max_daily_loss_pct_of_starting_equity=1.0,
            max_consecutive_losses=3,
            entry_start_time="09:30",
            latest_entry_time="15:30",
            cooldown_bars_after_exit=0,
        ),
        strategy=StrategyConfig(name="test_pulse", expected_version="0.1.0", params={}),
        report=ReportConfig(output_dir="runs", html=False),
    )


# ---------------------------------------------------------------------------
# Deterministic test strategies (injected; never registered globally)
# ---------------------------------------------------------------------------


class PulseParams(BaseStrictModel):
    emit_on_bar_index: int = Field(1, ge=1)
    stop_offset: float = Field(0.5, gt=0.0)
    target_offset: float = Field(1.0, gt=0.0)


class PulseStrategy(Strategy[PulseParams]):
    """Emits one long market intent with a bracket (stop + target)."""

    strategy_id = "test_pulse"
    strategy_version = "0.1.0"
    params_model = PulseParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Pulse",
            scope="per_symbol",
            warmup_bars=1,
        )

    def initialize(self, ctx: StrategyContext) -> None:
        self._bar_count = 0
        self._emitted = False

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        self._bar_count += 1
        if self._bar_count == self.params.emit_on_bar_index and not self._emitted:
            self._emitted = True
            return [
                ctx.create_intent(
                    symbol=bar.symbol,
                    direction="long",
                    intent_type="market",
                    stop_price=bar.close - self.params.stop_offset,
                    take_profit_price=bar.close + self.params.target_offset,
                )
            ]
        return []


class NoWarmupPulseStrategy(PulseStrategy):
    """Same as PulseStrategy but declares zero warmup bars (emits on bar 1)."""

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Pulse No Warmup",
            scope="per_symbol",
            warmup_bars=0,
        )


class CapturingStrategy(PulseStrategy):
    """Asserts the causal-context bound: history never exceeds engine time."""

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        hist = ctx.history(bar.symbol, 100)
        for past in hist:
            assert past.bar_end_utc <= ctx.engine_time_utc
        return super().on_bar(ctx, bar)


class FailingStrategy(PulseStrategy):
    """Emits on bar 1 then raises on bar 2 to test diagnostics retention."""

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Failing",
            scope="per_symbol",
            warmup_bars=0,
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if bar.bar_end_utc >= local_utc(9, 40):
            raise RuntimeError("boom")
        return super().on_bar(ctx, bar)


# ---------------------------------------------------------------------------
# 1. No same-bar fill (docs/08 §3 #1, ADR-007)
# ---------------------------------------------------------------------------


def test_no_same_bar_signal_fill() -> None:
    """An intent emitted at a bar close fills no earlier than the next bar open."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.2, high=100.6, low=100.0, close=100.4, volume=20_000),
        make_bar(hour=9, minute=50, open_=100.4, high=100.8, low=100.2, close=100.6, volume=20_000),
    ]
    # Bar 2 (09:35) closes at 100.0 and emits; the signal bar is bars[1].
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.status == "COMPLETED"
    assert len(result.intents) == 1
    assert result.intents[0].symbol == "AAA"
    # The single fill happens at the next bar's open (09:40), never on the
    # signal bar (09:35) whose close produced the intent.
    assert len(result.fills) == 1
    signal_bar_end = bars[1].bar_end_utc
    assert all(f.timestamp_utc > signal_bar_end for f in result.fills)
    assert result.fills[0].timestamp_utc == bars[2].bar_end_utc
    assert result.fills[0].fill_price == bars[2].open
    assert result.fills[0].order_id == result.orders[0].id


# ---------------------------------------------------------------------------
# 2. Exact event sequence (docs/04 §3, §13)
# ---------------------------------------------------------------------------


def test_exact_event_sequence_eligible_from_next_bar() -> None:
    """Intent -> risk decision -> order(eligible_from=signal bar end) -> next-bar fill."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        # Next bar: entry fills at open 99.5; low 99.2 stays above the 99.0
        # stop so the bracket's protective children are NOT touched on the
        # entry bar (isolating the sequencing property under test).
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.2, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=NoWarmupPulseStrategy(PulseParams(emit_on_bar_index=1))
    )
    assert result.status == "COMPLETED"

    # Step 6-9: the intent is recorded, risk accepted it, the accepted order
    # carries eligible_from = the signal bar's end (next bar start), and the
    # fill occurs at the following bar's open.
    assert len(result.intents) == 1
    assert len(result.decisions) == 1
    assert result.decisions[0].accepted
    # The broker book contains the entry plus its bracket children
    # (entry, -sl, -tp). The entry order is the one without a parent.
    entries = [o for o in result.orders if o.parent_order_id is None]
    assert len(entries) == 1
    order = entries[0]
    assert order.eligible_from_utc == bars[0].bar_end_utc
    assert order.status == "open" or order.status == "filled"
    assert len(result.fills) == 1
    assert result.fills[0].timestamp_utc == bars[1].bar_end_utc
    assert result.fills[0].fill_price == bars[1].open

    # Broker events must include the acceptance and the fill in order.
    event_types = [e.event_type for e in result.broker_events]
    assert "accepted" in event_types
    assert "filled" in event_types
    assert result.broker_events[0].event_type == "accepted"


# ---------------------------------------------------------------------------
# 3. Full bracket lifecycle through the engine (T420 integration)
# ---------------------------------------------------------------------------


def test_bracket_lifecycle_entry_then_target_exit() -> None:
    """Entry fills next open, target child later exits; position flat and reconciled."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        # Entry at next open 100.0; range stays inside stop 99.5 / target 101.0.
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        # Riser bar touches the 101.0 target -> protective child fills.
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
        make_bar(hour=9, minute=50, open_=101.0, high=101.3, low=100.8, close=101.1, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.status == "COMPLETED"
    # Entry (bracket) + target-exit fill.
    assert len(result.fills) == 2
    assert result.fills[0].order_id == result.orders[0].id
    assert result.fills[1].order_id == f"{result.orders[0].id}-tp"
    assert result.fills[1].fill_price == 101.0  # limit target touch
    # Position is flat; ledger reconciles; equity curve covers every bar.
    assert result.reconciliation is not None
    assert result.reconciliation.reconciled
    assert len(result.equity_curve) == len(bars)
    # The stop sibling was cancelled.
    sl_order = next(o for o in result.orders if o.id == f"{result.orders[0].id}-sl")
    assert sl_order.status == "cancelled"
    assert sl_order.reason == "SIBLING_FILLED"


# ---------------------------------------------------------------------------
# 4. Warmup isolation (docs/08 §3 #3, docs/04 §11)
# ---------------------------------------------------------------------------


def test_warmup_isolates_orders() -> None:
    """Warmup bars populate history but emit no orders, fills, or decisions."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    # Pulse has warmup_bars=1; the intent on bar 1 is suppressed.
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=1))
    )
    assert result.status == "COMPLETED"
    assert len(result.intents) == 1
    assert len(result.decisions) == 0
    assert len(result.orders) == 0
    assert len(result.fills) == 0
    assert any("WARMUP" in warning for warning in result.warnings)
    assert len(result.equity_curve) == len(bars)


# ---------------------------------------------------------------------------
# 5. Deterministic rerun (NFR-001)
# ---------------------------------------------------------------------------


def test_deterministic_rerun_identical_outputs() -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
    ]

    def run_once() -> EngineRunResult:
        return SingleSymbolEventEngine(
            make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
        ).run()

    first = run_once()
    second = run_once()
    assert first.status == second.status == "COMPLETED"
    assert first.fills == second.fills
    assert first.orders == second.orders
    assert first.broker_events == second.broker_events
    assert first.equity_curve == second.equity_curve
    assert first.decisions == second.decisions


# ---------------------------------------------------------------------------
# 6. Failure retains diagnostics (docs/02 §9, NFR-004)
# ---------------------------------------------------------------------------


def test_failure_retains_diagnostics_and_partial_state() -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=FailingStrategy(PulseParams(emit_on_bar_index=1))
    )
    assert result.status == "FAILED"
    assert result.error is not None
    assert "boom" in result.error
    # State recorded before the failure is preserved for diagnostics.
    assert len(result.intents) == 1
    assert len(result.decisions) == 1
    assert len(result.orders) == 1
    assert result.reconciliation is None


def test_failure_on_bad_data_contract() -> None:
    """Overlapping bars fail validation and the run carries the traceback."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0),
        # Overlaps the previous bar's interval.
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
    ]
    result = run_single_symbol_backtest(make_config(), bars, strategy=PulseStrategy(PulseParams()))
    assert result.status == "FAILED"
    assert result.error is not None
    assert "overlapping bars" in result.error or "duplicate bar" in result.error


def test_failure_on_multi_symbol_input() -> None:
    """The single-symbol engine refuses mixed-symbol input explicitly."""
    bars = [
        make_bar(symbol="AAA", hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(symbol="BBB", hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0),
    ]
    result = run_single_symbol_backtest(make_config(), bars, strategy=PulseStrategy(PulseParams()))
    assert result.status == "FAILED"
    assert result.error is not None
    assert "single-symbol" in result.error


# ---------------------------------------------------------------------------
# 7. Causal-context integration (docs/08 §3 #2)
# ---------------------------------------------------------------------------


def test_causal_context_never_exposes_future_bars() -> None:
    """A strategy's history never exceeds the engine clock through the engine."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.2, high=100.6, low=100.0, close=100.4, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=CapturingStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.status == "COMPLETED"
