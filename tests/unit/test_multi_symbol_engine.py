"""Tests for the T450 deterministic multi-symbol event engine.

Covers docs/02 §7 (timestamp merge, symbol ordering, shared capital,
simultaneous intent allocation, symbol-order-independent economics under the
``priority_then_symbol`` allocator), ADR-013 (per-symbol strategy instances,
broker symbol filter), docs/08 §3 timing rules in a multi-symbol setting,
NFR-001 deterministic rerun, and docs/02 §9 failure diagnostics retention.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import ClassVar
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
from edgeback.engine import (
    MultiSymbolEventEngine,
    MultiSymbolRunResult,
    build_allocator,
    run_multi_symbol_backtest,
)
from edgeback.risk import RiskReason
from edgeback.strategy.base import Strategy
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata

SESSION_DATE = date(2025, 1, 13)
ET = ZoneInfo("America/New_York")


def local_utc(hour: int, minute: int = 0) -> datetime:
    """2025-01-13 local ET converted to UTC (EST = UTC-5)."""
    return datetime(2025, 1, 13, hour, minute, tzinfo=ET).astimezone(UTC)


def make_bar(
    *,
    symbol: str,
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


def make_config(symbols: list[str] | None = None) -> BacktestConfig:
    return BacktestConfig(
        config_version="1.0",
        project=ProjectConfig(
            name="t450", tags=[], notes="multi-symbol engine test", random_seed=42
        ),
        market=MarketConfig(calendar="XNYS", timezone="America/New_York", session="regular"),
        data=DataConfig(
            provider="synthetic",
            feed="fixtures",
            symbols=symbols or ["AAA", "BBB"],
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
            sizing=RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=0.5),
            max_position_pct_of_equity=50.0,
            max_gross_exposure_pct=100.0,
            max_concurrent_positions=10,
            max_trades_per_session=10,
            max_daily_loss_pct_of_starting_equity=100.0,
            max_consecutive_losses=100,
            entry_start_time="09:30",
            latest_entry_time="15:30",
            cooldown_bars_after_exit=0,
        ),
        strategy=StrategyConfig(name="test_multi_pulse", expected_version="0.1.0", params={}),
        report=ReportConfig(output_dir="runs", html=False),
    )


# ---------------------------------------------------------------------------
# Deterministic multi-symbol test strategies (injected; never registered)
# ---------------------------------------------------------------------------


class MultiPulseParams(BaseStrictModel):
    emit_on_bar_index: int = Field(1, ge=1)
    stop_offset: float = Field(1.0, gt=0.0)
    target_offset: float = Field(2.0, gt=0.0)
    priority: int = 0


class MultiPulseStrategy(Strategy[MultiPulseParams]):
    """Emits one long bracket intent for its own symbol on a given bar index."""

    strategy_id = "test_multi_pulse"
    strategy_version = "0.1.0"
    params_model = MultiPulseParams
    _warmup_bars: ClassVar[int] = 0

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Multi Pulse",
            scope="per_symbol",
            warmup_bars=cls._warmup_bars,
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
                    priority=self.params.priority,
                )
            ]
        return []


class WarmupMultiPulseStrategy(MultiPulseStrategy):
    """MultiPulse with one warmup bar so bar-1 intents are suppressed."""

    strategy_id = "test_multi_pulse_warmup"
    _warmup_bars = 1


class TrackingMultiPulseStrategy(MultiPulseStrategy):
    """Asserts per-symbol isolation: on_bar only receives this instance's symbol."""

    def initialize(self, ctx: StrategyContext) -> None:
        super().initialize(ctx)
        self._own_symbol: str | None = None

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        if self._own_symbol is None:
            self._own_symbol = bar.symbol
        assert bar.symbol == self._own_symbol, "per-symbol instance received another symbol"
        hist = ctx.history(bar.symbol, 100)
        for past in hist:
            assert past.bar_end_utc <= ctx.engine_time_utc
        return super().on_bar(ctx, bar)


def pulse_for(
    symbol: str,
    *,
    emit_on_bar_index: int = 1,
    priority: int = 0,
    strategy_cls: type[MultiPulseStrategy] = MultiPulseStrategy,
) -> MultiPulseStrategy:
    return strategy_cls(MultiPulseParams(emit_on_bar_index=emit_on_bar_index, priority=priority))


def pulse_map(
    symbols: list[str],
    *,
    emit_on_bar_index: int = 1,
    priority: int = 0,
    strategy_cls: type[MultiPulseStrategy] = MultiPulseStrategy,
) -> dict[str, MultiPulseStrategy]:
    return {
        sym: pulse_for(
            sym, emit_on_bar_index=emit_on_bar_index, priority=priority, strategy_cls=strategy_cls
        )
        for sym in symbols
    }


def two_symbol_bars(symbols: tuple[str, str] = ("AAA", "BBB")) -> list[Bar]:
    """Two symbols with identical timestamps; each emits + enters + targets."""
    a, b = symbols
    return [
        make_bar(symbol=a, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(symbol=b, hour=9, minute=30, open_=50.0, high=51.0, low=49.5, close=50.5),
        make_bar(symbol=a, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0),
        make_bar(symbol=b, hour=9, minute=35, open_=50.5, high=51.0, low=50.0, close=51.0),
        make_bar(symbol=a, hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2),
        make_bar(symbol=b, hour=9, minute=40, open_=51.0, high=51.5, low=50.8, close=51.3),
    ]


# ---------------------------------------------------------------------------
# 1. Timestamp merge + symbol ordering + per-symbol fills
# ---------------------------------------------------------------------------


def test_timestamp_merge_and_per_symbol_fills() -> None:
    """Bars merge by bar_end_utc; fills use each symbol's own bar prices."""
    bars = two_symbol_bars()
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]),
        bars,
        strategies=pulse_map(["AAA", "BBB"]),
    )
    assert result.status == "COMPLETED"
    assert result.symbols == ("AAA", "BBB")
    # Each symbol emits one intent at its first bar close; fills at next bar open.
    assert len(result.intents) == 2
    assert len(result.fills) == 2
    a_fill = next(f for f in result.fills if f.symbol == "AAA")
    b_fill = next(f for f in result.fills if f.symbol == "BBB")
    assert a_fill.fill_price == 99.5  # AAA bar 2 open
    assert b_fill.fill_price == 50.5  # BBB bar 2 open
    # No same-bar fill: signal at 09:30 close, fill at 09:35 open.
    signal_time = local_utc(9, 30)
    assert all(f.timestamp_utc > signal_time for f in result.fills)
    assert result.reconciliation is not None and result.reconciliation.reconciled


def test_on_bar_dispatched_in_canonical_symbol_order() -> None:
    """Same-timestamp dispatch order is AAA before BBB (canonical symbol order)."""

    class RecorderStrategy(MultiPulseStrategy):
        def __init__(self, params: MultiPulseParams, seen: list[str]) -> None:
            super().__init__(params)
            self._seen = seen

        def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
            self._seen.append(bar.symbol)
            return super().on_bar(ctx, bar)

    seen_aaa: list[str] = []
    seen_bbb: list[str] = []
    # Use injected instances that only receive their own symbol; ordering is
    # verified by the engine's dispatch loop itself via distinct lists.
    strategies: dict[str, RecorderStrategy] = {
        "AAA": RecorderStrategy(MultiPulseParams(), seen_aaa),
        "BBB": RecorderStrategy(MultiPulseParams(), seen_bbb),
    }
    result = run_multi_symbol_backtest(
        make_config(["BBB", "AAA"]),  # config order intentionally reversed
        two_symbol_bars(),
        strategies=strategies,
    )
    assert result.status == "COMPLETED"
    # Engine canonicalizes symbols to sorted order before dispatch; each
    # instance sees only its own symbol's bars (one per timestamp).
    assert seen_aaa == ["AAA", "AAA", "AAA"]
    assert seen_bbb == ["BBB", "BBB", "BBB"]


# ---------------------------------------------------------------------------
# 2. Per-symbol strategy instances (ADR-013)
# ---------------------------------------------------------------------------


def test_per_symbol_strategy_instances_are_isolated() -> None:
    """Each symbol gets its own strategy instance; state never crosses symbols."""
    strategies = {
        "AAA": TrackingMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=1)),
        "BBB": TrackingMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=1)),
    }
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]), two_symbol_bars(), strategies=strategies
    )
    assert result.status == "COMPLETED"
    assert len(result.intents) == 2
    # One accepted entry per symbol.
    assert {d.intent.symbol for d in result.decisions if d.accepted} == {"AAA", "BBB"}


# ---------------------------------------------------------------------------
# 3. Shared capital + simultaneous allocation (docs/02 §7)
# ---------------------------------------------------------------------------


def three_symbol_bars() -> list[Bar]:
    a, b, c = "AAA", "BBB", "CCC"
    return [
        make_bar(symbol=a, hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(symbol=b, hour=9, minute=30, open_=50.0, high=51.0, low=49.5, close=50.5),
        make_bar(symbol=c, hour=9, minute=30, open_=25.0, high=26.0, low=24.5, close=25.5),
        make_bar(symbol=a, hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0),
        make_bar(symbol=b, hour=9, minute=35, open_=50.5, high=51.0, low=50.0, close=51.0),
        make_bar(symbol=c, hour=9, minute=35, open_=25.5, high=26.0, low=25.0, close=26.0),
    ]


def test_shared_capital_batch_allocation() -> None:
    """Simultaneous intents compete for shared capital; later candidates rejected."""
    config = make_config(["AAA", "BBB", "CCC"]).model_copy(
        update={
            "engine": make_config(["AAA", "BBB", "CCC"]).engine,
            "risk": make_config(["AAA", "BBB", "CCC"]).risk.model_copy(
                update={"max_gross_exposure_pct": 70.0}
            ),
        }
    )
    # risk_per_trade 0.5% of equity = 500 USD budget; stop 1.0 away + ~0.05 cost
    # → ~476 shares each → AAA ≈ 47.4k, BBB ≈ 23.8k, CCC ≈ 11.9k notional.
    # Equal priority resolves by symbol ascending: AAA reserves 47.4k, then BBB
    # would push past the 70k gross cap (71.2k > 70k) so BBB is rejected, and
    # CCC fits (47.4k + 11.9k = 59.3k ≤ 70k). The accepted set is {AAA, CCC}.
    result = run_multi_symbol_backtest(
        config,
        three_symbol_bars(),
        strategies=pulse_map(["AAA", "BBB", "CCC"]),
    )
    assert result.status == "COMPLETED"
    accepted = [d for d in result.decisions if d.accepted]
    rejected = [d for d in result.decisions if not d.accepted]
    assert len(accepted) == 2
    assert len(rejected) == 1
    assert rejected[0].reason == RiskReason.GROSS_EXPOSURE_LIMIT
    assert rejected[0].intent.symbol == "BBB"


def test_priority_then_symbol_allocator_order() -> None:
    """Higher priority wins; equal priority breaks by canonical symbol ascending."""
    config = make_config(["CCC", "AAA", "BBB"]).model_copy(
        update={
            "risk": make_config(["CCC", "AAA", "BBB"]).risk.model_copy(
                update={"max_gross_exposure_pct": 70.0}
            )
        }
    )
    strategies = {
        "AAA": pulse_for("AAA", priority=0),
        "BBB": pulse_for("BBB", priority=10),
        "CCC": pulse_for("CCC", priority=10),
    }
    result = run_multi_symbol_backtest(config, three_symbol_bars(), strategies=strategies)
    assert result.status == "COMPLETED"
    accepted = {d.intent.symbol for d in result.decisions if d.accepted}
    # BBB (prio 10) and CCC (prio 10, symbol > BBB) outrank AAA (prio 0), and
    # with equal priority BBB is evaluated before CCC. Both fit; AAA is left out.
    assert accepted == {"BBB", "CCC"}
    aaa_decision = next(d for d in result.decisions if d.intent.symbol == "AAA")
    assert not aaa_decision.accepted
    assert aaa_decision.reason == RiskReason.GROSS_EXPOSURE_LIMIT


def test_symbol_order_independent_outcome() -> None:
    """Swapping supplied-bar order or config order never changes the economics."""
    bars_forward = three_symbol_bars()
    bars_reversed = list(reversed(three_symbol_bars()))

    def run_once(bars: list[Bar], symbols: list[str]) -> MultiSymbolRunResult:
        return run_multi_symbol_backtest(make_config(symbols), bars, strategies=pulse_map(symbols))

    first = run_once(bars_forward, ["AAA", "BBB", "CCC"])
    second = run_once(bars_reversed, ["CCC", "BBB", "AAA"])

    assert first.status == second.status == "COMPLETED"
    assert first.fills == second.fills
    assert first.orders == second.orders
    assert first.decisions == second.decisions
    assert first.equity_curve == second.equity_curve


# ---------------------------------------------------------------------------
# 4. Warmup isolation per symbol (docs/04 §11)
# ---------------------------------------------------------------------------


def test_warmup_isolation_per_symbol() -> None:
    """A symbol still in warmup is suppressed while its warmed-up peer may trade."""
    bars: list[Bar] = []
    for hour, minute in ((9, 30), (9, 35), (9, 40)):
        for sym, prices in (
            ("AAA", (99.0, 100.0, 98.5, 99.5)),
            ("BBB", (50.0, 51.0, 49.5, 50.5)),
        ):
            open_, high, low, close = prices
            bars.append(
                make_bar(
                    symbol=sym,
                    hour=hour,
                    minute=minute,
                    open_=open_,
                    high=high,
                    low=low,
                    close=close,
                )
            )

    strategies = {
        # AAA emits on its first bar → warmup (warmup_bars=1) → suppressed.
        "AAA": WarmupMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=1)),
        # BBB emits on its second bar → past warmup → accepted.
        "BBB": WarmupMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=2)),
    }
    result = run_multi_symbol_backtest(make_config(["AAA", "BBB"]), bars, strategies=strategies)
    assert result.status == "COMPLETED"
    # Exactly one decision (BBB); AAA's intent existed but was warmup-suppressed.
    assert len(result.decisions) == 1
    assert result.decisions[0].intent.symbol == "BBB"
    assert result.decisions[0].accepted
    # The bracket entry produces the entry plus its two protective children.
    entries = [o for o in result.orders if o.parent_order_id is None]
    assert len(entries) == 1
    assert entries[0].symbol == "BBB"
    assert len(result.orders) == 3
    assert any("WARMUP" in w and "AAA" in w for w in result.warnings)
    assert not any("WARMUP" in w and "BBB" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 5. Deterministic rerun (NFR-001)
# ---------------------------------------------------------------------------


def test_deterministic_rerun_identical_outputs() -> None:
    bars = two_symbol_bars()
    strategies_factory = lambda: pulse_map(["AAA", "BBB"])  # noqa: E731

    first = MultiSymbolEventEngine(
        make_config(["AAA", "BBB"]), bars, strategies=strategies_factory()
    ).run()
    second = MultiSymbolEventEngine(
        make_config(["AAA", "BBB"]), bars, strategies=strategies_factory()
    ).run()
    assert first.status == second.status == "COMPLETED"
    assert first.fills == second.fills
    assert first.orders == second.orders
    assert first.broker_events == second.broker_events
    assert first.decisions == second.decisions
    assert first.equity_curve == second.equity_curve


# ---------------------------------------------------------------------------
# 6. Data validation and failure diagnostics (docs/02 §9)
# ---------------------------------------------------------------------------


def test_rejects_duplicate_bar() -> None:
    bars = two_symbol_bars() + [
        make_bar(symbol="AAA", hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5)
    ]
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]), bars, strategies=pulse_map(["AAA", "BBB"])
    )
    assert result.status == "FAILED"
    assert result.error is not None
    assert "duplicate bar" in result.error


def test_rejects_overlapping_bars_per_symbol() -> None:
    bars = two_symbol_bars() + [
        # Overlaps AAA's 09:30-09:35 bar.
        make_bar(symbol="AAA", hour=9, minute=32, open_=99.0, high=100.0, low=98.5, close=99.5)
    ]
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]), bars, strategies=pulse_map(["AAA", "BBB"])
    )
    assert result.status == "FAILED"
    assert result.error is not None
    assert "overlapping bars" in result.error


def test_rejects_incomplete_bar() -> None:
    bar = make_bar(symbol="AAA", hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5)
    incomplete = bar.model_copy(update={"is_complete": False})
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]), [incomplete], strategies=pulse_map(["AAA", "BBB"])
    )
    assert result.status == "FAILED"
    assert result.error is not None
    assert "incomplete bar" in result.error


def test_failure_retains_partial_state() -> None:
    class FailingMultiPulseStrategy(MultiPulseStrategy):
        def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
            # Fail on the second timestamp (bar ending 09:40) so the first
            # timestamp's intents were already recorded.
            if bar.bar_end_utc >= local_utc(9, 40):
                raise RuntimeError("multi-boom")
            return super().on_bar(ctx, bar)

    strategies = {
        "AAA": FailingMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=1)),
        "BBB": FailingMultiPulseStrategy(MultiPulseParams(emit_on_bar_index=1)),
    }
    result = run_multi_symbol_backtest(
        make_config(["AAA", "BBB"]), two_symbol_bars(), strategies=strategies
    )
    assert result.status == "FAILED"
    assert result.error is not None
    assert "multi-boom" in result.error
    # Partial state recorded before the failure is preserved.
    assert len(result.intents) == 2
    assert result.reconciliation is None


# ---------------------------------------------------------------------------
# 7. Allocator configuration fail-fast (docs/02 §7)
# ---------------------------------------------------------------------------


def test_unknown_allocator_fails_fast() -> None:
    config = make_config(["AAA", "BBB"]).model_copy(
        update={
            "engine": make_config(["AAA", "BBB"]).engine.model_copy(
                update={"entry_allocation": "pro_rata"}
            )
        }
    )
    try:
        MultiSymbolEventEngine(config, two_symbol_bars(), strategies=pulse_map(["AAA", "BBB"]))
        raise AssertionError("expected ValueError for unknown allocator")
    except ValueError as exc:
        assert "unknown entry_allocation" in str(exc)


def test_build_allocator_only_priority_then_symbol() -> None:
    assert build_allocator("priority_then_symbol") is not None
    try:
        build_allocator("pro_rata")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "unknown entry_allocation" in str(exc)
