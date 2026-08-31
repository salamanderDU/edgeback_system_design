"""Tests for T500 canonical run-result tables.

Covers ``docs/07_CLI_CONFIG_AND_ARTIFACTS.md`` §8-11 and
``docs/04_BACKTEST_ENGINE.md`` §6, §14:

- stable Parquet schemas for every canonical table;
- complete linkage: decisions→intents, orders→decisions, fills→orders,
  trades→entry/exit fills and orders, events→orders;
- trade construction matches the ledger's base-price accounting and cost
  decomposition (docs/04 §6);
- deterministic rerun produces identical tables (NFR-001);
- both single-symbol and multi-symbol engine results write unchanged;
- FAILED runs still produce truthful (``run_status=FAILED``) tables
  (docs/02 §9);
- empty runs produce valid zero-row tables.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import Field

from edgeback.artifacts.tables import trades_from_fills, write_run_tables
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
from edgeback.risk.manager import RiskReason
from edgeback.strategy.base import Strategy
from edgeback.strategy.context import StrategyContext
from edgeback.strategy.models import StrategyMetadata

SESSION_DATE = date(2025, 1, 13)
ET = ZoneInfo("America/New_York")

EXPECTED_TABLES = {
    "intents.parquet",
    "decisions.parquet",
    "orders.parquet",
    "order_events.parquet",
    "fills.parquet",
    "trades.parquet",
    "equity.parquet",
    "warnings.parquet",
}


# ---------------------------------------------------------------------------
# Fixtures (mirroring the engine test helpers)
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


def make_config(symbols: list[str] | None = None, force_flat: bool = False) -> BacktestConfig:
    return BacktestConfig(
        config_version="1.0",
        project=ProjectConfig(name="t500", tags=[], notes="artifact tables test", random_seed=42),
        market=MarketConfig(calendar="XNYS", timezone="America/New_York", session="regular"),
        data=DataConfig(
            provider="synthetic",
            feed="fixtures",
            symbols=symbols or ["AAA"],
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
                max_pct_of_bar_volume=100.0, on_exceed="reject"
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


class PulseParams(BaseStrictModel):
    emit_on_bar_index: int = Field(1, ge=1)
    stop_offset: float = Field(0.5, gt=0.0)
    target_offset: float = Field(1.0, gt=0.0)


class PulseStrategy(Strategy[PulseParams]):
    """Emits one long market intent with a bracket (stop + target) once."""

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
    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Pulse No Warmup",
            scope="per_symbol",
            warmup_bars=0,
        )


class FailingStrategy(NoWarmupPulseStrategy):
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


def _read(path: Path) -> tuple[pa.Schema, pa.Table]:
    read_table = pq.read_table(path)
    return read_table.schema, read_table


def _schema_columns(schema: pa.Schema) -> list[str]:
    return [field.name for field in schema]


# ---------------------------------------------------------------------------
# 1. Stable schemas + linkage on a completed single-symbol run
# ---------------------------------------------------------------------------


def test_write_run_tables_creates_all_files_with_stable_schemas(tmp_path: Path) -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 2  # entry + target exit

    written = write_run_tables(result, tmp_path)
    assert {p.name for p in written} == EXPECTED_TABLES
    assert all(p.exists() for p in written)

    # ------------------------------------------------------------------
    # Schema stability: exact column sets per table
    # ------------------------------------------------------------------
    _, intents = _read(tmp_path / "intents.parquet")
    assert _schema_columns(intents.schema) == [
        "intent_seq",
        "symbol",
        "direction",
        "intent_type",
        "limit_price",
        "stop_price",
        "take_profit_price",
        "requested_shares",
        "tag",
        "protective_exit",
        "priority",
        "strategy_id",
        "strategy_version",
        "run_status",
    ]

    _, decisions = _read(tmp_path / "decisions.parquet")
    assert _schema_columns(decisions.schema) == [
        "decision_seq",
        "intent_seq",
        "symbol",
        "direction",
        "intent_type",
        "accepted",
        "reason",
        "message",
        "sized_shares",
        "order_id",
        "strategy_id",
        "strategy_version",
        "run_status",
    ]

    _, orders = _read(tmp_path / "orders.parquet")
    assert _schema_columns(orders.schema) == [
        "order_id",
        "symbol",
        "direction",
        "order_type",
        "shares",
        "limit_price",
        "stop_price",
        "take_profit_price",
        "stop_loss_price",
        "status",
        "reason",
        "eligible_from_utc",
        "expires_at_utc",
        "parent_order_id",
        "priority",
        "creation_sequence",
        "strategy_id",
        "strategy_version",
        "run_status",
    ]

    _, events = _read(tmp_path / "order_events.parquet")
    assert _schema_columns(events.schema) == [
        "event_seq",
        "event_type",
        "timestamp_utc",
        "order_id",
        "symbol",
        "status",
        "reason",
        "parent_order_id",
        "creation_sequence",
        "strategy_id",
        "strategy_version",
        "run_status",
    ]

    _, fills = _read(tmp_path / "fills.parquet")
    assert _schema_columns(fills.schema) == [
        "fill_id",
        "order_id",
        "symbol",
        "timestamp_utc",
        "direction",
        "action",
        "shares",
        "fill_price",
        "commission_usd",
        "slippage_usd",
        "spread_usd",
        "total_cost_usd",
        "effective_price",
        "reason",
        "run_status",
    ]

    _, trades = _read(tmp_path / "trades.parquet")
    assert _schema_columns(trades.schema) == [
        "trade_seq",
        "symbol",
        "side",
        "entry_order_id",
        "entry_fill_id",
        "entry_timestamp_utc",
        "entry_price",
        "exit_order_id",
        "exit_fill_id",
        "exit_timestamp_utc",
        "exit_price",
        "shares",
        "realized_pnl",
        "entry_cost_usd",
        "exit_cost_usd",
        "total_cost_usd",
        "net_pnl",
        "exit_reason",
        "holding_seconds",
        "run_status",
    ]

    _, equity = _read(tmp_path / "equity.parquet")
    assert _schema_columns(equity.schema) == [
        "bar_end_utc",
        "cash",
        "equity",
        "gross_exposure",
        "net_exposure",
        "run_status",
    ]

    _, warnings = _read(tmp_path / "warnings.parquet")
    assert _schema_columns(warnings.schema) == [
        "warning_seq",
        "message",
        "run_status",
    ]

    # All timestamp columns are timezone-aware UTC at microsecond precision
    # (stable schema: no naive timestamps can leak into artifacts).
    for schema, name in [
        (orders.schema, "eligible_from_utc"),
        (orders.schema, "expires_at_utc"),
        (fills.schema, "timestamp_utc"),
        (equity.schema, "bar_end_utc"),
        (trades.schema, "entry_timestamp_utc"),
        (trades.schema, "exit_timestamp_utc"),
    ]:
        field = schema.field(name)
        assert pa.types.is_timestamp(field.type)
        assert field.type.tz == "UTC"


def test_linkage_fills_orders_decisions_intents(tmp_path: Path) -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    write_run_tables(result, tmp_path)

    fills = pq.read_table(tmp_path / "fills.parquet").to_pandas()
    orders = pq.read_table(tmp_path / "orders.parquet").to_pandas()
    decisions = pq.read_table(tmp_path / "decisions.parquet").to_pandas()
    intents = pq.read_table(tmp_path / "intents.parquet").to_pandas()
    events = pq.read_table(tmp_path / "order_events.parquet").to_pandas()

    order_ids = set(orders["order_id"])
    # Every fill references an existing order (docs/08 §4 accounting invariants).
    assert set(fills["order_id"]).issubset(order_ids)
    # Every event references an existing order.
    assert set(events["order_id"]).issubset(order_ids)
    # Accepted decisions carry an existing order id; rejected ones carry NULL.
    accepted = decisions[decisions["accepted"]]
    assert accepted["order_id"].notna().all()
    assert set(accepted["order_id"]).issubset(order_ids)
    rejected = decisions[~decisions["accepted"]]
    assert (rejected["order_id"].isna()).all()
    # Every decision maps to an emitted intent by seq.
    intent_seqs = set(intents["intent_seq"])
    assert set(decisions["intent_seq"]).issubset(intent_seqs)
    # Cost decomposition present on every fill (docs/04 §6).
    assert (fills["commission_usd"] >= 0).all()
    assert (fills["slippage_usd"] >= 0).all()
    assert (fills["spread_usd"] >= 0).all()
    # Reason codes are recorded (docs/07 §10).
    assert decisions["reason"].isin([r.value for r in RiskReason]).all()


def test_trades_linkage_and_reconciliation(tmp_path: Path) -> None:
    """Closed bracket round trip: one trade linking to entry/exit fills/orders."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.reconciliation is not None
    assert result.reconciliation.reconciled

    write_run_tables(result, tmp_path)
    trades = pq.read_table(tmp_path / "trades.parquet").to_pandas()
    fills = pq.read_table(tmp_path / "fills.parquet").to_pandas()
    pq.read_table(tmp_path / "orders.parquet").to_pandas()

    # One long round trip linked to the actual entry/target-exit fills.
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["side"] == "long"
    assert trade["shares"] == fills.iloc[0]["shares"]
    assert trade["entry_order_id"] == fills.iloc[0]["order_id"]
    assert trade["entry_fill_id"] == fills.iloc[0]["fill_id"]
    assert trade["exit_order_id"] == fills.iloc[1]["order_id"]
    assert trade["exit_fill_id"] == fills.iloc[1]["fill_id"]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["holding_seconds"] == (local_utc(9, 45) - local_utc(9, 40)).total_seconds()

    # Realized P&L uses base prices exactly like the ledger; when the run ends
    # flat every fill cost is attributed to a trade (docs/04 §6).
    assert trades["realized_pnl"].sum() == result.reconciliation.realized_pnl
    total_fill_cost = (fills["commission_usd"] + fills["slippage_usd"] + fills["spread_usd"]).sum()
    assert trades["total_cost_usd"].sum() == round(total_fill_cost, 2)
    assert trades["net_pnl"].sum() == round(result.reconciliation.realized_pnl - total_fill_cost, 2)


def test_trades_short_round_trip() -> None:
    """A short entry covered by a later buy-to-cover produces a short trade."""

    class ShortParams(BaseStrictModel):
        emit_on_bar_index: int = Field(1, ge=1)

    class ShortStrategy(Strategy[ShortParams]):
        strategy_id = "test_short_pulse"
        strategy_version = "0.1.0"
        params_model = ShortParams

        @classmethod
        def metadata(cls) -> StrategyMetadata:
            return StrategyMetadata(
                strategy_id=cls.strategy_id,
                version=cls.strategy_version,
                name="Test Short Pulse",
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
                # Short bracket: stop above, target below.
                return [
                    ctx.create_intent(
                        symbol=bar.symbol,
                        direction="short",
                        intent_type="market",
                        stop_price=bar.close + 0.5,
                        take_profit_price=bar.close - 1.0,
                    )
                ]
            return []

    bars = [
        make_bar(hour=9, minute=30, open_=100.0, high=100.5, low=99.5, close=100.0, volume=20_000),
        # Entry at next open 100.0; falls to target 99.0 by bar close.
        make_bar(hour=9, minute=35, open_=100.0, high=100.2, low=99.0, close=99.2, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=ShortStrategy(ShortParams(emit_on_bar_index=1))
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 2

    trades = trades_from_fills(result.fills, result.orders)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == "short"
    assert trade.entry_price == 100.0
    assert trade.exit_price == 99.0
    assert trade.shares == result.fills[0].shares
    assert trade.realized_pnl == round(trade.shares * (100.0 - 99.0), 2)
    assert "TAKE_PROFIT" in trade.exit_reason or trade.exit_reason == "TAKE_PROFIT"


def test_no_trade_when_position_stays_open(tmp_path: Path) -> None:
    """An open position at run end produces no closed-trade row (docs/04 §14)."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=NoWarmupPulseStrategy(PulseParams(emit_on_bar_index=2))
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 1  # entry only; position still open

    write_run_tables(result, tmp_path)
    trades = pq.read_table(tmp_path / "trades.parquet").to_pandas()
    assert len(trades) == 0


def test_forced_session_close_tagged_when_flat_enabled(tmp_path: Path) -> None:
    """Forced session-close fills and trades are tagged (docs/04 §10)."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    result = run_single_symbol_backtest(
        make_config(force_flat=True),
        bars,
        strategy=NoWarmupPulseStrategy(PulseParams(emit_on_bar_index=2)),
    )
    assert result.status == "COMPLETED"
    assert len(result.fills) == 2  # entry + forced session close

    write_run_tables(result, tmp_path)
    fills = pq.read_table(tmp_path / "fills.parquet").to_pandas()
    trades = pq.read_table(tmp_path / "trades.parquet").to_pandas()
    assert fills["reason"].iloc[-1] == "FORCED_SESSION_CLOSE"
    assert len(trades) == 1
    assert trades["exit_reason"].iloc[0] == "FORCED_SESSION_CLOSE"


def test_rejected_and_warmup_intents_recorded(tmp_path: Path) -> None:
    """Suppressed warmup intents and rejected intents appear with reasons."""
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
    ]
    # PulseStrategy emits on bar 1 but declares warmup_bars=1, so the intent is
    # suppressed (docs/04 §11): no decisions/orders/fills, warning recorded.
    result = run_single_symbol_backtest(
        make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=1))
    )
    assert result.status == "COMPLETED"
    assert len(result.decisions) == 0
    assert any("WARMUP" in w for w in result.warnings)

    write_run_tables(result, tmp_path)
    intents = pq.read_table(tmp_path / "intents.parquet").to_pandas()
    warnings = pq.read_table(tmp_path / "warnings.parquet").to_pandas()
    assert len(intents) == 1
    assert intents["run_status"].iloc[0] == "COMPLETED"
    assert len(warnings) >= 1
    assert warnings["message"].iloc[0].startswith("WARMUP")


# ---------------------------------------------------------------------------
# 2. Determinism (NFR-001)
# ---------------------------------------------------------------------------


def test_deterministic_rerun_identical_tables(tmp_path: Path) -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
        make_bar(hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2, volume=20_000),
        make_bar(hour=9, minute=45, open_=100.5, high=101.2, low=100.0, close=101.1, volume=20_000),
    ]

    def run_once() -> list[Path]:
        result = run_single_symbol_backtest(
            make_config(), bars, strategy=PulseStrategy(PulseParams(emit_on_bar_index=2))
        )
        assert result.status == "COMPLETED"
        out = tmp_path / f"run-{len(list(tmp_path.glob('run-*')))}"
        return write_run_tables(result, out)

    first_written = run_once()
    second_written = run_once()
    assert [p.name for p in first_written] == [p.name for p in second_written]
    for first, second in zip(first_written, second_written):
        assert first.read_bytes() == second.read_bytes()


# ---------------------------------------------------------------------------
# 3. Multi-symbol result support
# ---------------------------------------------------------------------------


def test_multi_symbol_result_writes_tables(tmp_path: Path) -> None:
    bars = [
        make_bar(symbol="AAA", hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(symbol="BBB", hour=9, minute=30, open_=50.0, high=50.5, low=49.5, close=50.2),
        make_bar(symbol="AAA", hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0),
        make_bar(symbol="BBB", hour=9, minute=35, open_=50.2, high=50.8, low=50.0, close=50.5),
        make_bar(symbol="AAA", hour=9, minute=40, open_=100.0, high=100.4, low=99.8, close=100.2),
        make_bar(symbol="BBB", hour=9, minute=40, open_=50.2, high=50.8, low=50.1, close=50.6),
    ]
    strategies = {
        "AAA": NoWarmupPulseStrategy(PulseParams(emit_on_bar_index=2)),
        "BBB": NoWarmupPulseStrategy(PulseParams(emit_on_bar_index=2)),
    }
    result = run_multi_symbol_backtest(make_config(["AAA", "BBB"]), bars, strategies=strategies)
    assert result.status == "COMPLETED"
    assert len(result.fills) == 2  # entry each symbol; no exits (force_flat=False)

    write_run_tables(result, tmp_path)
    intents = pq.read_table(tmp_path / "intents.parquet").to_pandas()
    fills = pq.read_table(tmp_path / "fills.parquet").to_pandas()
    orders = pq.read_table(tmp_path / "orders.parquet").to_pandas()
    assert set(intents["symbol"]) == {"AAA", "BBB"}
    assert set(fills["symbol"]) == {"AAA", "BBB"}
    assert set(orders["symbol"]) == {"AAA", "BBB"}
    # Open positions -> no closed trades.
    trades = pq.read_table(tmp_path / "trades.parquet").to_pandas()
    assert len(trades) == 0


# ---------------------------------------------------------------------------
# 4. FAILED runs are still truthful artifacts (docs/02 §9)
# ---------------------------------------------------------------------------


def test_failed_result_writes_tables_with_failed_status(tmp_path: Path) -> None:
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

    written = write_run_tables(result, tmp_path)
    assert {p.name for p in written} == EXPECTED_TABLES
    for name in EXPECTED_TABLES:
        table = pq.read_table(tmp_path / name)
        if "run_status" in table.column_names and table.num_rows > 0:
            assert set(table.column("run_status").to_pylist()) == {"FAILED"}


# ---------------------------------------------------------------------------
# 5. Empty runs produce valid zero-row tables
# ---------------------------------------------------------------------------


class SilentStrategy(PulseStrategy):
    """Never emits an intent; exercises zero-row table writers."""

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Test Silent",
            scope="per_symbol",
            warmup_bars=0,
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        return []


def test_empty_result_writes_valid_zero_row_tables(tmp_path: Path) -> None:
    bars = [
        make_bar(hour=9, minute=30, open_=99.0, high=100.0, low=98.5, close=99.5, volume=20_000),
        make_bar(hour=9, minute=35, open_=99.5, high=100.0, low=99.0, close=100.0, volume=20_000),
    ]
    result = run_single_symbol_backtest(make_config(), bars, strategy=SilentStrategy(PulseParams()))
    assert result.status == "COMPLETED"
    assert len(result.intents) == 0
    assert len(result.fills) == 0

    written = write_run_tables(result, tmp_path)
    assert {p.name for p in written} == EXPECTED_TABLES
    for name in EXPECTED_TABLES:
        table = pq.read_table(tmp_path / name)
        if name == "equity.parquet":
            assert table.num_rows == len(bars)
        else:
            assert table.num_rows == 0
