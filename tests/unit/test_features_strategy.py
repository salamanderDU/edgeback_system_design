from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from edgeback.config import resolve_config
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.domain import IdAllocator, PortfolioSnapshot
from edgeback.strategy import StrategyContext, create_strategy, describe_strategy, list_strategies

ROOT = Path(__file__).parents[2]


def test_strategy_registry_lists_and_describes_all_seed_strategies() -> None:
    listed = list_strategies()
    assert [item["strategy_id"] for item in listed] == [
        "gap_momentum",
        "opening_range_breakout",
        "vwap_mean_reversion",
    ]
    detail = describe_strategy("opening_range_breakout")
    assert detail["version"] == "0.1.0"
    assert "opening_range_minutes" in detail["parameter_schema"]["properties"]


def test_causal_context_hides_future_bars_and_returns_copies() -> None:
    bars = generate_fixture_bars(symbols=("AAA",), session_count=1)
    current = bars[10]
    ids = IdAllocator()
    snapshot = PortfolioSnapshot(
        timestamp_utc=current.bar_end_utc,
        cash_usd=100_000,
        equity_usd=100_000,
        gross_exposure_usd=0,
        net_exposure_usd=0,
        realized_pnl_usd=0,
        unrealized_pnl_usd=0,
        total_costs_usd=0,
    )
    ctx = StrategyContext(
        strategy_id="test",
        strategy_version="0.1.0",
        engine_time_utc=current.bar_end_utc,
        session_date=current.session_date,
        current_bar=current,
        histories={"AAA": bars},
        portfolio=snapshot,
        intent_id_factory=ids.next_intent,
    )
    history = ctx.history("AAA")
    assert history[-1].bar_end_utc == current.bar_end_utc
    assert len(history) == 11
    mutable = list(history)
    mutable.clear()
    assert len(ctx.history("AAA")) == 11


def test_orb_signal_is_invariant_to_future_mutation() -> None:
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=["AAA"])
    bars = generate_fixture_bars(symbols=("AAA",), session_count=2)
    signal_bar = next(
        bar
        for bar in bars
        if bar.session_date == date(2025, 1, 7)
        and bar.bar_end_utc.time() == datetime(2025, 1, 7, 14, 50, tzinfo=UTC).time()
    )
    upto = tuple(bar for bar in bars if bar.bar_end_utc <= signal_bar.bar_end_utc)
    future_changed = tuple(
        bar.model_copy(update={"close": bar.close * 1.5, "high": max(bar.high, bar.close * 1.5)})
        if bar.bar_end_utc > signal_bar.bar_end_utc
        else bar
        for bar in bars
    )

    def get_signal(dataset: tuple) -> tuple:
        strategy = create_strategy(config.strategy.name, config.strategy.params, "0.1.0")
        ids = IdAllocator()
        snapshot = PortfolioSnapshot(
            timestamp_utc=signal_bar.bar_end_utc,
            cash_usd=100_000,
            equity_usd=100_000,
            gross_exposure_usd=0,
            net_exposure_usd=0,
            realized_pnl_usd=0,
            unrealized_pnl_usd=0,
            total_costs_usd=0,
        )
        strategy.on_session_start(
            StrategyContext(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                engine_time_utc=datetime(2025, 1, 7, 14, 30, tzinfo=UTC),
                session_date=date(2025, 1, 7),
                current_bar=None,
                histories={"AAA": tuple(bar for bar in dataset if bar.session_date < date(2025, 1, 7))},
                portfolio=snapshot,
                intent_id_factory=ids.next_intent,
            )
        )
        emitted = []
        for bar in dataset:
            if bar.session_date != date(2025, 1, 7) or bar.bar_end_utc > signal_bar.bar_end_utc:
                continue
            history = tuple(item for item in dataset if item.bar_end_utc <= bar.bar_end_utc)
            ctx = StrategyContext(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                engine_time_utc=bar.bar_end_utc,
                session_date=bar.session_date,
                current_bar=bar,
                histories={"AAA": history},
                portfolio=snapshot,
                intent_id_factory=ids.next_intent,
            )
            emitted.extend(strategy.on_bar(ctx, bar))
        return tuple((item.side, item.signal_time_utc, item.stop_loss_price) for item in emitted)

    assert get_signal(upto) == get_signal(future_changed)


def _manual_bar(
    symbol: str,
    start: datetime,
    *,
    session_date: date,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 100,
) -> object:
    from edgeback.domain import Bar

    return Bar(
        symbol=symbol,
        provider_symbol=symbol,
        interval_seconds=300,
        bar_start_utc=start,
        bar_end_utc=start + timedelta(minutes=5),
        session_date=session_date,
        session_type="regular",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source_provider="fixture",
        source_feed="fixture",
        adjustment_mode="raw",
        ingested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _context_for(strategy: object, current: object, history: tuple, ids: IdAllocator) -> StrategyContext:
    snapshot = PortfolioSnapshot(
        timestamp_utc=current.bar_end_utc,
        cash_usd=100_000,
        equity_usd=100_000,
        gross_exposure_usd=0,
        net_exposure_usd=0,
        realized_pnl_usd=0,
        unrealized_pnl_usd=0,
        total_costs_usd=0,
    )
    return StrategyContext(
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        engine_time_utc=current.bar_end_utc,
        session_date=current.session_date,
        current_bar=current,
        histories={current.symbol: history},
        portfolio=snapshot,
        intent_id_factory=ids.next_intent,
    )


def test_vwap_mean_reversion_emits_causal_long_intent() -> None:
    strategy = create_strategy(
        "vwap_mean_reversion",
        {
            "earliest_entry_time": "09:30",
            "latest_entry_time": "15:00",
            "deviation_atr_multiple": 0.5,
            "atr_period": 14,
            "maximum_vwap_slope_bps_per_bar": 100.0,
            "stop_atr_multiple": 1.0,
            "target": "vwap",
            "max_trades_per_symbol_session": 2,
        },
        "0.1.0",
    )
    day = date(2026, 1, 6)
    start = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)
    bars = [
        _manual_bar(
            "AAA",
            start + timedelta(minutes=5 * index),
            session_date=day,
            open_=100,
            high=101,
            low=99,
            close=100,
        )
        for index in range(14)
    ]
    bars.append(
        _manual_bar(
            "AAA",
            start + timedelta(minutes=70),
            session_date=day,
            open_=100,
            high=100,
            low=95,
            close=96,
        )
    )
    ids = IdAllocator()
    strategy.on_session_start(_context_for(strategy, bars[0], (bars[0],), ids))
    intents = strategy.on_bar(strategy_ctx := _context_for(strategy, bars[-1], tuple(bars), ids), bars[-1])
    assert strategy_ctx.history("AAA")[-1] == bars[-1]
    assert len(intents) == 1
    assert intents[0].side.value == "buy"
    assert intents[0].reason_code == "VWAP_LONG_REVERSION"
    assert intents[0].take_profit_price > bars[-1].close
    assert intents[0].stop_loss_price < bars[-1].close


def test_gap_momentum_requires_confirmation_and_volume() -> None:
    strategy = create_strategy(
        "gap_momentum",
        {
            "minimum_gap_pct": 1.0,
            "maximum_gap_pct": 8.0,
            "confirmation_minutes": 15,
            "confirmation_breakout_buffer_bps": 0.0,
            "minimum_volume_ratio": 1.2,
            "stop_atr_multiple": 1.0,
            "reward_risk": 1.5,
            "latest_entry_time": "11:30",
        },
        "0.1.0",
    )
    previous_day = date(2026, 1, 5)
    current_day = date(2026, 1, 6)
    previous_start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    current_start = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)
    previous = [
        _manual_bar(
            "AAA",
            previous_start + timedelta(minutes=5 * index),
            session_date=previous_day,
            open_=100,
            high=101,
            low=99,
            close=100,
            volume=100,
        )
        for index in range(20)
    ]
    current = [
        _manual_bar(
            "AAA",
            current_start + timedelta(minutes=5 * index),
            session_date=current_day,
            open_=102,
            high=103,
            low=101,
            close=102.5,
            volume=100,
        )
        for index in range(3)
    ]
    breakout = _manual_bar(
        "AAA",
        current_start + timedelta(minutes=15),
        session_date=current_day,
        open_=102.5,
        high=105,
        low=102,
        close=104,
        volume=200,
    )
    ids = IdAllocator()
    all_seen = list(previous)
    strategy.on_session_start(_context_for(strategy, current[0], tuple(previous + [current[0]]), ids))
    for item in current:
        all_seen.append(item)
        assert strategy.on_bar(_context_for(strategy, item, tuple(all_seen), ids), item) == []
    all_seen.append(breakout)
    intents = strategy.on_bar(_context_for(strategy, breakout, tuple(all_seen), ids), breakout)
    assert len(intents) == 1
    assert intents[0].reason_code == "GAP_UP_MOMENTUM"
    assert intents[0].take_profit_price > breakout.close
    assert intents[0].stop_loss_price < breakout.close
