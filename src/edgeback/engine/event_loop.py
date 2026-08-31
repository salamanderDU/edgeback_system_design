from __future__ import annotations

import traceback
from collections import defaultdict
from datetime import UTC, date, datetime
from itertools import groupby
from typing import Any

from edgeback.calendar import TradingCalendar, XNYSCalendar
from edgeback.config.models import ResolvedConfig
from edgeback.data.schema import bars_to_frame
from edgeback.data.validation import validate_bars
from edgeback.domain import (
    Bar,
    EquityPoint,
    IdAllocator,
    OrderEvent,
    OrderIntent,
    RunStatus,
    WarningEvent,
)
from edgeback.engine.state import BacktestResult
from edgeback.errors import SimulationError
from edgeback.execution import ExecutionCosts, SimulatedBroker
from edgeback.portfolio import PortfolioLedger
from edgeback.risk import RiskContext, RiskDecision, RiskManager, RiskReason
from edgeback.strategy import Strategy, StrategyContext, create_strategy


class EventEngine:
    def __init__(self, config: ResolvedConfig, *, calendar: TradingCalendar | None = None) -> None:
        self.config = config
        self.calendar = calendar or XNYSCalendar()

    def run(
        self,
        bars: tuple[Bar, ...] | list[Bar],
        *,
        trade_session_dates: set[date] | None = None,
    ) -> BacktestResult:
        result = BacktestResult(status=RunStatus.RUNNING)
        try:
            canonical_bars = self._validate_input(tuple(bars))
            ids = IdAllocator()
            ledger = PortfolioLedger(
                self.config.engine.initial_cash_usd,
                ids,
                max_leverage=self.config.engine.max_leverage,
            )
            risk = RiskManager(self.config.risk, self.config.engine, self.config.execution, ids)
            broker = SimulatedBroker(
                ExecutionCosts(self.config.execution),
                ids,
                same_bar_policy=self.config.engine.same_bar_bracket_policy,
            )
            histories: dict[str, list[Bar]] = {symbol: [] for symbol in self.config.data.symbols}
            strategies: dict[str, Strategy[Any]] = {
                symbol: create_strategy(
                    self.config.strategy.name,
                    self.config.strategy.params,
                    self.config.strategy.expected_version,
                )
                for symbol in self.config.data.symbols
            }
            first_time = canonical_bars[0].bar_start_utc
            for symbol, strategy in strategies.items():
                strategy.initialize(
                    self._context(
                        strategy,
                        ids,
                        first_time,
                        canonical_bars[0].session_date,
                        None,
                        histories,
                        ledger.snapshot(first_time),
                    )
                )

            by_session: dict[date, list[Bar]] = defaultdict(list)
            for bar in canonical_bars:
                by_session[bar.session_date].append(bar)
            for session_date in sorted(by_session):
                session = self.calendar.session(session_date)
                session_bars = sorted(
                    by_session[session_date], key=lambda item: (item.bar_end_utc, item.symbol)
                )
                risk.on_session_start(session_date, ledger.snapshot(session.open_utc).equity_usd)
                trading_enabled = trade_session_dates is None or session_date in trade_session_dates
                for symbol in self.config.data.symbols:
                    strategies[symbol].on_session_start(
                        self._context(
                            strategies[symbol],
                            ids,
                            session.open_utc,
                            session_date,
                            None,
                            histories,
                            ledger.snapshot(session.open_utc),
                        )
                    )

                final_bars: dict[str, Bar] = {}
                for timestamp, grouped in groupby(session_bars, key=lambda item: item.bar_end_utc):
                    bars_at_timestamp = sorted(list(grouped), key=lambda item: item.symbol)
                    current_by_symbol = {bar.symbol: bar for bar in bars_at_timestamp}
                    # 1-4: eligible orders, fills, accounting, bracket activation.
                    broker_result = broker.evaluate_bars(bars_at_timestamp)
                    result.order_events.extend(broker_result.events)
                    result.warnings.extend(broker_result.warnings)
                    intervals = {bar.symbol: bar.interval_seconds for bar in bars_at_timestamp}
                    for fill in broker_result.fills:
                        result.fills.append(fill)
                        closed = ledger.apply_fill(fill)
                        for trade in closed:
                            risk.observe_closed_trade(
                                trade.symbol,
                                trade.net_pnl_usd,
                                trade.exit_time_utc,
                                intervals[fill.symbol],
                            )
                    for bar in bars_at_timestamp:
                        final_bars[bar.symbol] = bar

                    # Current completed bars become causal history at timestamp T.
                    for bar in bars_at_timestamp:
                        histories[bar.symbol].append(bar)
                    snapshot = ledger.mark_to_market(
                        {bar.symbol: bar.close for bar in bars_at_timestamp}, timestamp
                    )
                    self._dispatch_order_updates(
                        broker_result.events,
                        broker,
                        strategies,
                        ids,
                        timestamp,
                        session_date,
                        current_by_symbol,
                        histories,
                        snapshot,
                    )

                    intents_at_timestamp: list[OrderIntent] = []
                    for bar in bars_at_timestamp:
                        strategy = strategies[bar.symbol]
                        ctx = self._context(
                            strategy,
                            ids,
                            timestamp,
                            session_date,
                            bar,
                            histories,
                            snapshot,
                        )
                        emitted = strategy.on_bar(ctx, bar)
                        result.intents.extend(emitted)
                        warmup = strategy.metadata().warmup_bars
                        if len(histories[bar.symbol]) <= warmup or not trading_enabled:
                            for intent in emitted:
                                decision = RiskDecision(
                                    intent=intent,
                                    accepted=False,
                                    reason=RiskReason.WARMUP,
                                )
                                result.risk_decisions.append(decision)
                                result.warnings.append(
                                    WarningEvent(
                                        warning_id=ids.next_warning(),
                                        timestamp_utc=timestamp,
                                        code=(
                                            "WARMUP_INTENT_SUPPRESSED"
                                            if trading_enabled
                                            else "RESEARCH_WARMUP_INTENT_SUPPRESSED"
                                        ),
                                        message=(
                                            "Strategy intent was suppressed during warmup."
                                            if trading_enabled
                                            else "Strategy intent was suppressed outside the research trade window."
                                        ),
                                        symbol=bar.symbol,
                                        context={"intent_id": intent.intent_id},
                                    )
                                )
                        else:
                            intents_at_timestamp.extend(emitted)

                    if intents_at_timestamp:
                        risk_context = RiskContext(
                            timestamp_utc=timestamp,
                            session_date=session_date,
                            session_close_utc=session.close_utc,
                            interval_seconds=bars_at_timestamp[0].interval_seconds,
                            portfolio=snapshot,
                            reference_prices={
                                symbol: bar.close for symbol, bar in current_by_symbol.items()
                            },
                            bar_volumes={
                                symbol: bar.volume for symbol, bar in current_by_symbol.items()
                            },
                            open_order_symbols=broker.open_order_symbols(),
                        )
                        decisions = risk.evaluate_batch(intents_at_timestamp, risk_context)
                        result.risk_decisions.extend(decisions)
                        for decision in decisions:
                            if decision.accepted:
                                events = broker.submit(decision.orders)
                                result.order_events.extend(events)
                                self._dispatch_order_updates(
                                    events,
                                    broker,
                                    strategies,
                                    ids,
                                    timestamp,
                                    session_date,
                                    current_by_symbol,
                                    histories,
                                    ledger.snapshot(timestamp),
                                )

                    point_snapshot = ledger.snapshot(timestamp)
                    result.equity.append(
                        EquityPoint(
                            timestamp_utc=timestamp,
                            session_date=str(session_date),
                            cash_usd=point_snapshot.cash_usd,
                            equity_usd=point_snapshot.equity_usd,
                            gross_exposure_usd=point_snapshot.gross_exposure_usd,
                            net_exposure_usd=point_snapshot.net_exposure_usd,
                            realized_pnl_usd=point_snapshot.realized_pnl_usd,
                            unrealized_pnl_usd=point_snapshot.unrealized_pnl_usd,
                            total_costs_usd=point_snapshot.total_costs_usd,
                        )
                    )

                if self.config.engine.force_flat_at_session_end:
                    forced = broker.force_flat(ledger.positions(), final_bars)
                    result.order_events.extend(forced.events)
                    result.warnings.extend(forced.warnings)
                    for fill in forced.fills:
                        result.fills.append(fill)
                        closed = ledger.apply_fill(fill)
                        for trade in closed:
                            risk.observe_closed_trade(
                                trade.symbol,
                                trade.net_pnl_usd,
                                trade.exit_time_utc,
                                final_bars[trade.symbol].interval_seconds,
                            )
                    if final_bars:
                        close_time = max(bar.bar_end_utc for bar in final_bars.values())
                        close_snapshot = ledger.snapshot(close_time)
                        self._dispatch_order_updates(
                            forced.events,
                            broker,
                            strategies,
                            ids,
                            close_time,
                            session_date,
                            final_bars,
                            histories,
                            close_snapshot,
                        )
                        result.equity.append(
                            EquityPoint(
                                timestamp_utc=close_time,
                                session_date=str(session_date),
                                cash_usd=close_snapshot.cash_usd,
                                equity_usd=close_snapshot.equity_usd,
                                gross_exposure_usd=close_snapshot.gross_exposure_usd,
                                net_exposure_usd=close_snapshot.net_exposure_usd,
                                realized_pnl_usd=close_snapshot.realized_pnl_usd,
                                unrealized_pnl_usd=close_snapshot.unrealized_pnl_usd,
                                total_costs_usd=close_snapshot.total_costs_usd,
                            )
                        )
                canceled_events = broker.cancel_session_orders(session.close_utc)
                self._dispatch_order_updates(
                    canceled_events,
                    broker,
                    strategies,
                    ids,
                    session.close_utc,
                    session_date,
                    final_bars,
                    histories,
                    ledger.snapshot(session.close_utc),
                )
                for symbol, strategy in strategies.items():
                    end_intents = strategy.on_session_end(
                        self._context(
                            strategy,
                            ids,
                            session.close_utc,
                            session_date,
                            final_bars.get(symbol),
                            histories,
                            ledger.snapshot(session.close_utc),
                        )
                    )
                    if end_intents:
                        result.intents.extend(end_intents)
                        result.warnings.append(
                            WarningEvent(
                                warning_id=ids.next_warning(),
                                timestamp_utc=session.close_utc,
                                code="SESSION_END_INTENT_NOT_EXECUTED",
                                message="No next regular-session bar exists for a session-end intent.",
                                symbol=symbol,
                                context={"intent_ids": [item.intent_id for item in end_intents]},
                            )
                        )

            final_time = canonical_bars[-1].bar_end_utc
            for symbol, strategy in strategies.items():
                strategy.finalize(
                    self._context(
                        strategy,
                        ids,
                        final_time,
                        canonical_bars[-1].session_date,
                        None,
                        histories,
                        ledger.snapshot(final_time),
                    )
                )
                result.strategy_states[symbol] = strategy.serializable_state()
            result.orders = list(broker.orders)
            result.order_events = list(broker.events)
            result.trades = list(ledger.trades)
            result.final_snapshot = ledger.snapshot(final_time)
            result.reconciliation = ledger.reconcile()
            if not bool(result.reconciliation.get("reconciled")):
                raise SimulationError("Portfolio reconciliation failed")
            result.status = RunStatus.COMPLETED
            return result
        except Exception as exc:
            result.status = RunStatus.FAILED
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            result.traceback_text = traceback.format_exc()
            return result

    def _dispatch_order_updates(
        self,
        events: tuple[OrderEvent, ...] | list[OrderEvent],
        broker: SimulatedBroker,
        strategies: dict[str, Strategy[Any]],
        ids: IdAllocator,
        timestamp: datetime,
        session_date: date,
        current_bars: dict[str, Bar],
        histories: dict[str, list[Bar]],
        snapshot: Any,
    ) -> None:
        for event in events:
            order = broker.order(event.order_id)
            strategy = strategies.get(order.symbol)
            if strategy is None or order.strategy_id == "__engine__":
                continue
            strategy.on_order_update(
                self._context(
                    strategy,
                    ids,
                    timestamp,
                    session_date,
                    current_bars.get(order.symbol),
                    histories,
                    snapshot,
                ),
                event,
            )

    def _validate_input(self, bars: tuple[Bar, ...]) -> tuple[Bar, ...]:
        if not bars:
            raise SimulationError("Backtest requires at least one bar")
        expected_order = tuple(sorted(bars, key=lambda item: (item.bar_end_utc, item.symbol)))
        if bars != expected_order:
            raise SimulationError("Input bars must already be sorted; engine will not silently repair them")
        keys = [(bar.symbol, bar.interval_seconds, bar.bar_start_utc) for bar in bars]
        if len(keys) != len(set(keys)):
            raise SimulationError("Input contains duplicate canonical bar keys")
        configured_symbols = set(self.config.data.symbols)
        observed_symbols = {bar.symbol for bar in bars}
        if observed_symbols != configured_symbols:
            raise SimulationError(
                f"Dataset symbols {sorted(observed_symbols)} do not match config {sorted(configured_symbols)}"
            )
        if any(bar.interval_seconds != self.config.data.interval_seconds for bar in bars):
            raise SimulationError("Dataset interval does not match resolved config")
        if any(not bar.is_complete for bar in bars):
            raise SimulationError("Incomplete bars cannot be simulated")
        if any(bar.source_provider != self.config.data.provider for bar in bars):
            # Fixture is an explicit test-only provider exception.
            if not all(bar.source_provider == "fixture" for bar in bars):
                raise SimulationError("Dataset provider does not match resolved config")
        if any(bar.source_feed != self.config.data.feed for bar in bars):
            if not all(bar.source_feed == "fixture" for bar in bars):
                raise SimulationError("Dataset feed does not match resolved config")
        report = validate_bars(
            bars_to_frame(bars),
            calendar=self.calendar,
            minimum_session_completeness_pct=0.0,
            missing_session_policy="warn",
            now=datetime(2262, 1, 1, tzinfo=UTC),
        )
        if not report.passed:
            raise SimulationError(
                "Engine input validation failed: "
                + ", ".join(issue.code for issue in report.errors)
            )
        return bars

    @staticmethod
    def _context(
        strategy: Strategy[Any],
        ids: IdAllocator,
        timestamp: datetime,
        session_date: date,
        current_bar: Bar | None,
        histories: dict[str, list[Bar]],
        snapshot: Any,
    ) -> StrategyContext:
        return StrategyContext(
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            engine_time_utc=timestamp,
            session_date=session_date,
            current_bar=current_bar,
            histories={symbol: tuple(items) for symbol, items in histories.items()},
            portfolio=snapshot,
            intent_id_factory=ids.next_intent,
        )


def run_backtest(
    config: ResolvedConfig,
    bars: tuple[Bar, ...] | list[Bar],
    *,
    calendar: TradingCalendar | None = None,
    trade_session_dates: set[date] | None = None,
) -> BacktestResult:
    return EventEngine(config, calendar=calendar).run(
        bars, trade_session_dates=trade_session_dates
    )
