"""Deterministic multi-symbol event engine (T450).

Implements ``docs/02_ARCHITECTURE.md`` §7 and ``docs/04_BACKTEST_ENGINE.md``
§2-3 for multiple canonical symbols sharing one portfolio:

1. bars are merged by ``bar_end_utc``;
2. for each timestamp the broker evaluates eligible working orders for the
   bars ending at that timestamp in deterministic order, with only orders
   whose ``order.symbol`` equals the bar's symbol being matched (ADR-013);
3. fills are applied to the shared ledger and closed trades feed the risk
   counters;
4. portfolio and risk state are marked to market using each symbol's close;
5. per-symbol ``on_bar`` callbacks are invoked in canonical symbol order
   (one strategy instance per symbol, ADR-013), each through a causal
   context that still exposes the full multi-symbol history;
6. all emitted intents are risk-checked **as a batch** through the configured
   allocator (``priority_then_symbol``, docs/02 §7) against projected shared
   capital so symbol dispatch order cannot change the accepted set;
7. accepted orders receive ``eligible_from_utc = bar_end_utc`` (next-bar
   start, ADR-007) and are submitted to the broker;
8. state (intents, decisions, orders, fills, equity) is appended.
"""

from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from edgeback.config.models import BacktestConfig
from edgeback.domain.bars import Bar
from edgeback.domain.fills import Fill
from edgeback.domain.orders import Order, OrderEvent, OrderIntent
from edgeback.domain.positions import Position
from edgeback.engine.allocation import AllocationContext, IntentAllocator, build_allocator
from edgeback.engine.event_loop import EngineError, EquityPoint
from edgeback.execution import ExecutionCosts, SimulatedBroker, build_execution_costs
from edgeback.portfolio import PortfolioLedger, ReconciliationReport
from edgeback.risk import RiskContext, RiskDecision, RiskManager, risk_manager_from_config
from edgeback.strategy.base import Strategy
from edgeback.strategy.history import CausalStrategyContext
from edgeback.strategy.registry import get_strategy_class

logger = logging.getLogger(__name__)

__all__ = [
    "MultiSymbolEventEngine",
    "MultiSymbolRunResult",
    "run_multi_symbol_backtest",
]


@dataclass
class _MultiSymbolState:
    """Accumulated multi-symbol engine output; retained on failure for diagnostics."""

    symbols: tuple[str, ...] = ()
    strategy_id: str = ""
    strategy_version: str = ""
    intents: list[OrderIntent] = field(default_factory=list)
    decisions: list[RiskDecision] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    events: list[OrderEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)


@dataclass(frozen=True)
class MultiSymbolRunResult:
    """Complete deterministic result of a multi-symbol engine run.

    On failure (``status == "FAILED"``) ``error`` carries the retained
    traceback and the tuple fields hold whatever was recorded before the
    failure so diagnostics are preserved (docs/02 §9).
    """

    symbols: tuple[str, ...]
    status: str
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


class MultiSymbolEventEngine:
    """Deterministic event engine for multiple canonical symbols sharing capital."""

    def __init__(
        self,
        config: BacktestConfig,
        bars: Sequence[Bar],
        strategies: dict[str, Strategy[Any]] | None = None,
    ) -> None:
        self._config = config
        self._bars = list(bars)
        self._costs: ExecutionCosts = build_execution_costs(config.execution)
        self._allocator: IntentAllocator = build_allocator(config.engine.entry_allocation)
        self._injected_strategies = strategies
        self._state = _MultiSymbolState()

    def run(self) -> MultiSymbolRunResult:
        self._state = _MultiSymbolState()
        try:
            return self._run(self._state)
        except Exception as exc:  # noqa: BLE001
            logger.error("multi-symbol engine run failed: %s", exc)
            return self._failed_result(traceback.format_exc())

    def _run(self, state: _MultiSymbolState) -> MultiSymbolRunResult:
        bars = self._validate_bars(self._bars)
        symbols = tuple(sorted({b.symbol for b in bars}))
        by_symbol = {sym: [b for b in bars if b.symbol == sym] for sym in symbols}

        ledger = PortfolioLedger(
            initial_cash=self._config.engine.initial_cash_usd,
            max_leverage=self._config.engine.max_leverage,
        )
        broker = SimulatedBroker(
            self._costs, same_bar_policy=self._config.engine.same_bar_bracket_policy
        )
        risk = risk_manager_from_config(self._config.risk, self._config.execution)
        strategies = self._build_strategies(symbols, by_symbol)
        meta = next(iter(strategies.values())).metadata()
        warmup_bars = meta.warmup_bars

        state.symbols = symbols
        state.strategy_id = meta.strategy_id
        state.strategy_version = meta.version

        # Group bars by timestamp (bar_end_utc) merging across symbols.
        at_timestamp: dict[datetime, list[Bar]] = defaultdict(list)
        for bar in bars:
            at_timestamp[bar.bar_end_utc].append(bar)
        timestamps = sorted(at_timestamp)

        # Track per-symbol bars seen for warmup isolation.
        bars_seen: dict[str, int] = {sym: 0 for sym in symbols}

        session_start_realized = 0.0
        session_start_equity = 0.0
        synced_event_count = 0
        apply_seq = 0
        session_bars_accum: list[Bar] = []

        for idx, ts in enumerate(timestamps):
            ts_bars = at_timestamp[ts]
            session_date = ts_bars[0].session_date
            is_session_start = (
                idx == 0 or at_timestamp[timestamps[idx - 1]][0].session_date != session_date
            )
            is_session_end = (
                idx == len(timestamps) - 1
                or at_timestamp[timestamps[idx + 1]][0].session_date != session_date
            )

            if is_session_start:
                session_bars_accum = list(ts_bars)
                session_start_realized = ledger.realized_pnl
                session_start_equity = ledger.equity()
                risk.on_session_start(session_start_equity)
                for sym in symbols:
                    strategies[sym].on_session_start(CausalStrategyContext(ts, by_symbol))
            else:
                session_bars_accum.extend(ts_bars)

            # 2-4: broker evaluates eligible orders for all bars at this timestamp.
            positions_before = ledger.positions()
            broker_warning_count = len(broker.warnings)
            for bar in sorted(ts_bars, key=lambda b: b.symbol):
                bar_fills = broker.on_bar(bar)
                for fill in bar_fills:
                    apply_seq += 1
                    ledger.apply_fill(fill, order_id=apply_seq)
                    state.fills.append(fill)
            state.events.extend(broker.events[synced_event_count:])
            synced_event_count = len(broker.events)
            state.warnings.extend(broker.warnings[broker_warning_count:])

            self._record_closed_trades(risk, positions_before, ledger)
            for bar in ts_bars:
                ledger.mark_to_market(bar.symbol, bar.close)
            risk.on_bar()

            # 5: per-symbol on_bar in canonical symbol order. Symbols without a
            # bar at this timestamp are skipped (a merged feed may be sparse).
            emitted: list[OrderIntent] = []
            for sym in symbols:
                sym_bar = next((b for b in ts_bars if b.symbol == sym), None)
                if sym_bar is None:
                    continue
                bars_seen[sym] += 1
                ctx = CausalStrategyContext(ts, by_symbol)
                emitted.extend(strategies[sym].on_bar(ctx, sym_bar))
            state.intents.extend(emitted)

            # Per-symbol warmup isolation (docs/04 §11, ADR-013): an intent is
            # suppressed only while *its own symbol's* strategy instance is
            # still in warmup; warmed-up symbols may trade.
            post_warmup: list[OrderIntent] = []
            for intent in emitted:
                if bars_seen[intent.symbol] <= warmup_bars:
                    state.warnings.append(
                        f"WARMUP at {ts.isoformat()} symbol={intent.symbol}: "
                        f"{intent.direction} {intent.intent_type} intent suppressed"
                    )
                else:
                    post_warmup.append(intent)

            if post_warmup:
                session_pnl = (ledger.realized_pnl - session_start_realized) + sum(
                    ledger.unrealized_pnl(open_symbol) for open_symbol in ledger.positions()
                )
                reference_prices = {b.symbol: b.close for b in ts_bars}
                risk_ctx = RiskContext(
                    equity=ledger.equity(),
                    cash=ledger.cash,
                    positions=ledger.positions(),
                    gross_exposure=ledger.gross_exposure(),
                    reference_prices=reference_prices,
                    session_pnl=round(session_pnl, 2),
                    current_time_utc=ts,
                    session_date=session_date,
                    bar_volumes={b.symbol: b.volume for b in ts_bars},
                    estimated_cost_per_share_by_symbol={
                        b.symbol: self._estimated_round_trip_cost_per_share(b.close)
                        for b in ts_bars
                    },
                    start_equity=session_start_equity,
                )

                alloc_ctx = AllocationContext(intents=tuple(post_warmup), risk=risk, ctx=risk_ctx)
                for decision in self._allocator.allocate(alloc_ctx):
                    state.decisions.append(decision)
                    if decision.accepted and decision.order is not None:
                        order = decision.order.model_copy(update={"eligible_from_utc": ts})
                        broker.submit(order, now_utc=ts)
                        state.orders.append(order)
                        state.events.extend(broker.events[synced_event_count:])
                        synced_event_count = len(broker.events)

            state.equity_curve.append(self._equity_point(ts, ledger))

            # docs/04 §10 (T460): engine-generated forced session-close
            # liquidation on the final bars of a session. Each symbol is
            # liquidated at its own final bar close (the calendar-provided
            # close; no hard-coded 16:00), after strategy dispatch so no
            # strategy can request a same-close fill (ADR-007).
            if is_session_end and self._config.engine.force_flat_at_session_end:
                for sym in symbols:
                    final_bar = next(
                        (b for b in reversed(session_bars_accum) if b.symbol == sym), None
                    )
                    if final_bar is None:
                        continue
                    positions_before_close = ledger.positions()
                    broker_warning_count = len(broker.warnings)
                    close_fills = broker.force_flat_at_close(ledger.positions(), final_bar)
                    for fill in close_fills:
                        apply_seq += 1
                        ledger.apply_fill(fill, order_id=apply_seq)
                        state.fills.append(fill)
                    state.events.extend(broker.events[synced_event_count:])
                    synced_event_count = len(broker.events)
                    state.warnings.extend(broker.warnings[broker_warning_count:])
                    if close_fills:
                        self._record_closed_trades(risk, positions_before_close, ledger)
                        ledger.mark_to_market(sym, final_bar.close)
                        state.equity_curve.append(self._equity_point(final_bar.bar_end_utc, ledger))

            # Session-end lifecycle (docs/04 §13): after forced liquidation.
            if is_session_end:
                self._session_end(strategies, by_symbol, ts)

        for sym in symbols:
            strategies[sym].finalize(CausalStrategyContext(timestamps[-1], by_symbol))

        state.orders = broker.orders()
        reconciliation = ledger.reconcile()
        logger.info(
            "multi-symbol engine run completed symbols=%s fills=%d orders=%d",
            ",".join(symbols),
            len(state.fills),
            len(state.orders),
        )

        return MultiSymbolRunResult(
            symbols=symbols,
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

    def _session_end(
        self,
        strategies: dict[str, Strategy[Any]],
        by_symbol: dict[str, list[Bar]],
        last_ts: datetime,
    ) -> None:
        ctx = CausalStrategyContext(last_ts, by_symbol)
        for sym in by_symbol:
            strategies[sym].on_session_end(ctx)

    def _failed_result(self, error: str) -> MultiSymbolRunResult:
        state = self._state
        return MultiSymbolRunResult(
            symbols=tuple(getattr(state, "symbols", ())),
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
        ordered = sorted(bars, key=lambda b: (b.bar_start_utc, b.bar_end_utc, b.symbol))
        seen: set[tuple[str, datetime]] = set()
        for i, bar in enumerate(ordered):
            if not bar.is_complete:
                raise EngineError(
                    f"incomplete bar passed to engine at {bar.bar_end_utc.isoformat()}"
                )
            key = (bar.symbol, bar.bar_start_utc)
            if key in seen:
                raise EngineError(f"duplicate bar at {bar.bar_start_utc.isoformat()}")
            seen.add(key)
            if i > 0:
                prev = ordered[i - 1]
                if prev.symbol == bar.symbol and bar.bar_start_utc < prev.bar_end_utc:
                    raise EngineError(f"overlapping bars at {prev.bar_end_utc.isoformat()}")
        return ordered

    @staticmethod
    def _group_sessions(bars: Sequence[Bar]) -> list[tuple[date, list[Bar]]]:
        groups: dict[date, list[Bar]] = {}
        order: list[date] = []
        for bar in bars:
            if bar.session_date not in groups:
                groups[bar.session_date] = []
                order.append(bar.session_date)
            groups[bar.session_date].append(bar)
        return [(session_date, groups[session_date]) for session_date in order]

    def _build_strategies(
        self, symbols: tuple[str, ...], by_symbol: dict[str, list[Bar]]
    ) -> dict[str, Strategy[Any]]:
        if self._injected_strategies is not None:
            missing = set(symbols) - set(self._injected_strategies)
            if missing:
                raise EngineError(f"missing injected strategies for symbols: {sorted(missing)}")
            strategies = dict(self._injected_strategies)
        else:
            strategy_cls = get_strategy_class(self._config.strategy.name)
            if strategy_cls.strategy_version != self._config.strategy.expected_version:
                raise EngineError(
                    f"strategy version mismatch: configured expected_version="
                    f"{self._config.strategy.expected_version!r} but registered "
                    f"{strategy_cls.strategy_id!r} is {strategy_cls.strategy_version!r}"
                )
            params = strategy_cls.params_model.model_validate(self._config.strategy.params)
            strategies = {sym: strategy_cls(params) for sym in symbols}
        for sym, strategy in strategies.items():
            strategy.initialize(CausalStrategyContext(by_symbol[sym][0].bar_end_utc, by_symbol))
        return strategies

    def _estimated_round_trip_cost_per_share(self, price: float) -> float:
        try:
            deco = self._costs.decompose(base_price=price, shares=1, action="buy")
            one_side = deco.total_cost_usd
        except Exception:
            return 0.0
        return round(2 * one_side, 4)


def run_multi_symbol_backtest(
    config: BacktestConfig,
    bars: Sequence[Bar],
    strategies: dict[str, Strategy[Any]] | None = None,
) -> MultiSymbolRunResult:
    """Convenience entry point for a deterministic multi-symbol backtest."""
    return MultiSymbolEventEngine(config, bars, strategies=strategies).run()
