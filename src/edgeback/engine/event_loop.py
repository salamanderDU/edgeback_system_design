"""
Deterministic single-symbol event engine (T440).

Implements ``docs/04_BACKTEST_ENGINE.md`` §2-3,13 for one symbol:

1. the engine clock advances to the bar's end time ``T``;
2. the broker evaluates eligible working orders against the completed bar;
3. fills are applied to the portfolio ledger in broker order;
4. closed trades are recorded to the risk manager and the ledger/risk state is
   marked to market at the completed bar close;
5. the strategy receives the completed bar through a causal context;
6. the strategy emits zero or more :class:`OrderIntent` objects;
7. risk validates/sizes the emitted intents as a batch;
8. accepted orders are submitted to the broker with
   ``eligible_from_utc = bar_end_utc`` (the next bar start), so a signal
   created from a bar close can never fill on that same bar (docs/04 §3,
   ADR-007);
9. state (intents, decisions, orders, fills, equity) is appended.

Warmup isolation (docs/04 §11) is driven by the strategy's declared
``warmup_bars``: during the first ``warmup_bars`` completed bars for the
symbol the strategy still receives bars (so history populates) but emitted
intents are suppressed and recorded with the reason ``WARMUP``.

The engine is deterministic and offline: it never fetches data, never reads
the network, and depends only on the resolved configuration plus the supplied
canonical bars. Order/fill ordering is deterministic (docs/04 §12); no global
RNG is used. Session-close liquidation is deliberately out of scope for T440
(docs/04 §10 is covered by task T460).
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from edgeback.config.models import BacktestConfig
from edgeback.domain.bars import Bar
from edgeback.domain.fills import Fill
from edgeback.domain.orders import Order, OrderEvent, OrderIntent
from edgeback.domain.positions import Position
from edgeback.execution import ExecutionCosts, SimulatedBroker, build_execution_costs
from edgeback.portfolio import PortfolioLedger, ReconciliationReport
from edgeback.risk import RiskContext, RiskDecision, RiskManager, risk_manager_from_config
from edgeback.strategy.base import Strategy
from edgeback.strategy.history import CausalStrategyContext
from edgeback.strategy.registry import get_strategy_class

logger = logging.getLogger(__name__)

__all__ = [
    "EngineError",
    "EquityPoint",
    "EngineRunResult",
    "SingleSymbolEventEngine",
    "run_single_symbol_backtest",
]


class EngineError(Exception):
    """Raised when a backtest violates a documented engine/data contract."""


@dataclass(frozen=True)
class EquityPoint:
    """Deterministic per-bar portfolio snapshot (docs/04 §14)."""

    timestamp_utc: datetime
    cash: float
    equity: float
    gross_exposure: float
    net_exposure: float


@dataclass(frozen=True)
class EngineRunResult:
    """
    Complete deterministic result of a single-symbol engine run.

    On failure (``status == "FAILED"``) ``error`` carries the retained
    traceback and the tuple fields hold whatever was recorded before the
    failure so diagnostics are preserved (docs/02 §9).
    """

    symbol: str
    status: Literal["COMPLETED", "FAILED"]
    error: str | None
    strategy_id: str
    strategy_version: str
    intents: tuple[OrderIntent, ...]
    decisions: tuple[RiskDecision, ...]
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    broker_events: tuple[OrderEvent, ...]
    warnings: tuple[str, ...]
    equity_curve: tuple[EquityPoint, ...]
    reconciliation: ReconciliationReport | None


@dataclass
class _RunState:
    """Accumulated engine output; retained on failure for diagnostics."""

    symbol: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    intents: list[OrderIntent] = None  # type: ignore[assignment]
    decisions: list[RiskDecision] = None  # type: ignore[assignment]
    orders: list[Order] = None  # type: ignore[assignment]
    fills: list[Fill] = None  # type: ignore[assignment]
    events: list[OrderEvent] = None  # type: ignore[assignment]
    warnings: list[str] = None  # type: ignore[assignment]
    equity_curve: list[EquityPoint] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.intents = []
        self.decisions = []
        self.orders = []
        self.fills = []
        self.events = []
        self.warnings = []
        self.equity_curve = []


class SingleSymbolEventEngine:
    """
    Deterministic event engine for exactly one canonical symbol.

    Parameters
    ----------
    config
        Fully resolved backtest configuration.
    bars
        Chronological canonical bars for the single symbol (completed bars
        only; incomplete bars are rejected).
    strategy
        Optional pre-built strategy instance. When omitted, the engine builds
        the strategy from ``config.strategy`` through the trusted registry and
        validates the configured expected version.
    """

    def __init__(
        self,
        config: BacktestConfig,
        bars: Sequence[Bar],
        strategy: Strategy[Any] | None = None,
    ) -> None:
        self._config = config
        self._bars = list(bars)
        self._costs: ExecutionCosts = build_execution_costs(config.execution)
        self._injected_strategy = strategy
        self._state = _RunState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> EngineRunResult:
        """
        Run the backtest and return its deterministic result.

        Exceptions are caught and returned as ``status == "FAILED"`` with the
        retained traceback and partial state so callers (and artifact writers)
        can persist diagnostics without losing the run (docs/02 §9,
        NFR-004).
        """
        self._state = _RunState()
        try:
            return self._run(self._state)
        except Exception as exc:  # noqa: BLE001 — failures are retained, not masked
            logger.error("engine run failed: %s", exc)
            return self._failed_result(traceback.format_exc())

    # ------------------------------------------------------------------
    # Run implementation (docs/04 §13 pseudocode)
    # ------------------------------------------------------------------

    def _run(self, state: _RunState) -> EngineRunResult:
        bars = self._validate_bars(self._bars)
        symbol = bars[0].symbol
        sessions = self._group_sessions(bars)

        ledger = PortfolioLedger(
            initial_cash=self._config.engine.initial_cash_usd,
            max_leverage=self._config.engine.max_leverage,
        )
        broker = SimulatedBroker(
            self._costs, same_bar_policy=self._config.engine.same_bar_bracket_policy
        )
        risk = risk_manager_from_config(self._config.risk, self._config.execution)
        strategy = (
            self._injected_strategy
            if self._injected_strategy is not None
            else self._build_strategy()
        )

        meta = strategy.metadata()
        state.symbol = symbol
        state.strategy_id = meta.strategy_id
        state.strategy_version = meta.version
        warmup_bars = meta.warmup_bars

        strategy.initialize(CausalStrategyContext(bars[0].bar_end_utc, {symbol: bars}))

        apply_seq = 0
        bars_seen = 0
        session_start_realized = 0.0
        session_start_equity = 0.0
        synced_event_count = 0

        logger.info(
            "engine run started strategy=%s version=%s symbol=%s sessions=%d bars=%d",
            meta.strategy_id,
            meta.version,
            symbol,
            len(sessions),
            len(bars),
        )

        for session_date, session_bars in sessions:
            session_start_realized = ledger.realized_pnl
            session_start_equity = ledger.equity()
            risk.on_session_start(session_start_equity)
            strategy.on_session_start(
                CausalStrategyContext(session_bars[0].bar_end_utc, {symbol: bars})
            )

            for bar in session_bars:
                bars_seen += 1
                engine_time = bar.bar_end_utc

                # 2-4: broker evaluates eligible orders; ledger applies fills.
                positions_before = ledger.positions()
                broker_warning_count = len(broker.warnings)
                bar_fills = broker.on_bar(bar)
                for fill in bar_fills:
                    apply_seq += 1
                    ledger.apply_fill(fill, order_id=apply_seq)
                    state.fills.append(fill)
                # Sync broker lifecycle events emitted since the last sync
                # (acceptances from earlier submits AND fills from on_bar).
                state.events.extend(broker.events[synced_event_count:])
                synced_event_count = len(broker.events)
                state.warnings.extend(broker.warnings[broker_warning_count:])

                # 4b: closed trades feed risk counters; ledger+risk marked to market.
                self._record_closed_trades(risk, positions_before, ledger)
                ledger.mark_to_market(symbol, bar.close)
                risk.on_bar()

                # 5-8: strategy dispatch, risk batch evaluation, next-bar submit.
                ctx = CausalStrategyContext(engine_time, {symbol: bars})
                emitted = strategy.on_bar(ctx, bar)
                state.intents.extend(emitted)

                if bars_seen <= warmup_bars:
                    for intent in emitted:
                        state.warnings.append(
                            f"WARMUP at {engine_time.isoformat()} symbol={symbol}: "
                            f"{intent.direction} {intent.intent_type} intent suppressed"
                        )
                    state.equity_curve.append(self._equity_point(engine_time, ledger))
                    continue

                session_pnl = (ledger.realized_pnl - session_start_realized) + sum(
                    ledger.unrealized_pnl(open_symbol) for open_symbol in ledger.positions()
                )
                risk_ctx = RiskContext(
                    equity=ledger.equity(),
                    cash=ledger.cash,
                    positions=ledger.positions(),
                    gross_exposure=ledger.gross_exposure(),
                    reference_prices={symbol: bar.close},
                    session_pnl=round(session_pnl, 2),
                    current_time_utc=engine_time,
                    session_date=bar.session_date,
                    bar_volume=bar.volume,
                    estimated_cost_per_share=self._estimated_round_trip_cost_per_share(bar.close),
                    start_equity=session_start_equity,
                )
                for intent in emitted:
                    decision = risk.evaluate(intent, risk_ctx)
                    state.decisions.append(decision)
                    if decision.accepted and decision.order is not None:
                        order = decision.order.model_copy(update={"eligible_from_utc": engine_time})
                        broker.submit(order, now_utc=engine_time)
                        state.orders.append(order)
                        # Sync the acceptance event emitted by submit().
                        state.events.extend(broker.events[synced_event_count:])
                        synced_event_count = len(broker.events)

                state.equity_curve.append(self._equity_point(engine_time, ledger))

            strategy.on_session_end(
                CausalStrategyContext(session_bars[-1].bar_end_utc, {symbol: bars})
            )

        strategy.finalize(CausalStrategyContext(bars[-1].bar_end_utc, {symbol: bars}))
        state.orders = broker.orders()
        reconciliation = ledger.reconcile()
        logger.info(
            "engine run completed symbol=%s fills=%d orders=%d",
            symbol,
            len(state.fills),
            len(state.orders),
        )

        return EngineRunResult(
            symbol=symbol,
            status="COMPLETED",
            error=None,
            strategy_id=state.strategy_id,
            strategy_version=state.strategy_version,
            intents=tuple(state.intents),
            decisions=tuple(state.decisions),
            orders=tuple(state.orders),
            fills=tuple(state.fills),
            broker_events=tuple(state.events),
            warnings=tuple(state.warnings),
            equity_curve=tuple(state.equity_curve),
            reconciliation=reconciliation,
        )

    # ------------------------------------------------------------------
    # Failure diagnostics
    # ------------------------------------------------------------------

    def _failed_result(self, error: str) -> EngineRunResult:
        state = self._state
        return EngineRunResult(
            symbol=state.symbol,
            status="FAILED",
            error=error,
            strategy_id=state.strategy_id,
            strategy_version=state.strategy_version,
            intents=tuple(state.intents),
            decisions=tuple(state.decisions),
            orders=tuple(state.orders),
            fills=tuple(state.fills),
            broker_events=tuple(state.events),
            warnings=tuple(state.warnings),
            equity_curve=tuple(state.equity_curve),
            reconciliation=None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_strategy(self) -> Strategy[Any]:
        strategy_cls = get_strategy_class(self._config.strategy.name)
        if strategy_cls.strategy_version != self._config.strategy.expected_version:
            raise EngineError(
                f"strategy version mismatch: configured expected_version="
                f"{self._config.strategy.expected_version!r} but registered "
                f"{strategy_cls.strategy_id!r} is {strategy_cls.strategy_version!r}"
            )
        params = strategy_cls.params_model.model_validate(self._config.strategy.params)
        return strategy_cls(params)

    def _estimated_round_trip_cost_per_share(self, price: float) -> float:
        """Documented estimate used by risk-per-trade sizing (docs/04 §8)."""
        try:
            deco = self._costs.decompose(base_price=price, shares=1, action="buy")
            one_side = deco.total_cost_usd
        except Exception:
            return 0.0
        return round(2 * one_side, 4)

    @staticmethod
    def _equity_point(engine_time: datetime, ledger: PortfolioLedger) -> EquityPoint:
        return EquityPoint(
            timestamp_utc=engine_time,
            cash=ledger.cash,
            equity=ledger.equity(),
            gross_exposure=ledger.gross_exposure(),
            net_exposure=ledger.net_exposure(),
        )

    @staticmethod
    def _record_closed_trades(
        risk: RiskManager,
        positions_before: dict[str, Position],
        ledger: PortfolioLedger,
    ) -> None:
        """
        Record a completed round trip to the risk manager's session counters.

        A position is 'closed' when an open position becomes flat after the
        broker fills were applied. The realized P&L recorded is the per-symbol
        ledger realized P&L delta (base-price P&L; costs flow through cash).
        """
        for symbol, pos_before in positions_before.items():
            if pos_before.shares == 0:
                continue
            pos_after = ledger.position(symbol)
            if pos_after.shares == 0:
                realized = round(pos_after.realized_pnl - pos_before.realized_pnl, 2)
                risk.record_trade(realized)

    @staticmethod
    def _validate_bars(bars: Sequence[Bar]) -> list[Bar]:
        if not bars:
            raise EngineError("no bars supplied to the engine")
        ordered = sorted(bars, key=lambda b: (b.bar_start_utc, b.bar_end_utc))
        symbols = {b.symbol for b in ordered}
        if len(symbols) != 1:
            raise EngineError(f"single-symbol engine received symbols: {sorted(symbols)}")
        for i, bar in enumerate(ordered):
            if not bar.is_complete:
                raise EngineError(
                    f"incomplete bar passed to engine at {bar.bar_end_utc.isoformat()}"
                )
            if i > 0:
                prev = ordered[i - 1]
                if bar.bar_start_utc < prev.bar_end_utc:
                    raise EngineError(f"overlapping bars at {prev.bar_end_utc.isoformat()}")
                if bar.bar_start_utc == prev.bar_start_utc:
                    raise EngineError(f"duplicate bar at {prev.bar_start_utc.isoformat()}")
        return ordered

    @staticmethod
    def _group_sessions(bars: Sequence[Bar]) -> list[tuple[date, list[Bar]]]:
        """Group bars by session date preserving first-seen session order."""
        groups: dict[date, list[Bar]] = {}
        order: list[date] = []
        for bar in bars:
            if bar.session_date not in groups:
                groups[bar.session_date] = []
                order.append(bar.session_date)
            groups[bar.session_date].append(bar)
        return [(session_date, groups[session_date]) for session_date in order]


def run_single_symbol_backtest(
    config: BacktestConfig,
    bars: Sequence[Bar],
    strategy: Strategy[Any] | None = None,
) -> EngineRunResult:
    """Convenience entry point for a deterministic single-symbol backtest."""
    return SingleSymbolEventEngine(config, bars, strategy=strategy).run()
