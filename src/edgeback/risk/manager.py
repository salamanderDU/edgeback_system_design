from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import Field

from edgeback.config.models import EngineConfig, ExecutionConfig, RiskConfig
from edgeback.domain import (
    IdAllocator,
    IntentType,
    Order,
    OrderIntent,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    Side,
)
from edgeback.domain.common import DomainModel
from edgeback.execution.costs import ExecutionCosts

_ET = ZoneInfo("America/New_York")


class RiskReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    RESIZED = "RESIZED"
    OUTSIDE_ENTRY_WINDOW = "OUTSIDE_ENTRY_WINDOW"
    DIRECTION_NOT_ALLOWED = "DIRECTION_NOT_ALLOWED"
    DAILY_LOSS_LOCKOUT = "DAILY_LOSS_LOCKOUT"
    MAX_TRADES = "MAX_TRADES"
    MAX_CONSECUTIVE_LOSSES = "MAX_CONSECUTIVE_LOSSES"
    INVALID_STOP = "INVALID_STOP"
    INVALID_REFERENCE_PRICE = "INVALID_REFERENCE_PRICE"
    ZERO_QUANTITY = "ZERO_QUANTITY"
    POSITION_LIMIT = "POSITION_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    CASH_LIMIT = "CASH_LIMIT"
    MAX_CONCURRENT_POSITIONS = "MAX_CONCURRENT_POSITIONS"
    VOLUME_PARTICIPATION_EXCEEDED = "VOLUME_PARTICIPATION_EXCEEDED"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    NO_POSITION = "NO_POSITION"
    COOLDOWN = "COOLDOWN"
    WARMUP = "WARMUP"


class RiskContext(DomainModel):
    timestamp_utc: datetime
    session_date: date
    session_close_utc: datetime
    interval_seconds: int = Field(gt=0)
    portfolio: PortfolioSnapshot
    reference_prices: dict[str, float]
    bar_volumes: dict[str, int]
    open_order_symbols: tuple[str, ...] = ()


class RiskDecision(DomainModel):
    intent: OrderIntent
    accepted: bool
    reason: RiskReason
    quantity: int = Field(default=0, ge=0)
    estimated_risk_usd: float | None = None
    orders: tuple[Order, ...] = ()
    details: dict[str, float | int | str] = Field(default_factory=dict)


class RiskManager:
    def __init__(
        self,
        risk: RiskConfig,
        engine: EngineConfig,
        execution: ExecutionConfig,
        ids: IdAllocator,
    ) -> None:
        self.config = risk
        self.engine = engine
        self.costs = ExecutionCosts(execution)
        self.ids = ids
        self._session_date: date | None = None
        self._session_start_equity = 0.0
        self._trades = 0
        self._consecutive_losses = 0
        self._cooldown_until: dict[str, datetime] = {}

    def on_session_start(self, session_date: date, starting_equity: float) -> None:
        self._session_date = session_date
        self._session_start_equity = starting_equity
        self._trades = 0
        self._consecutive_losses = 0
        self._cooldown_until.clear()

    def observe_closed_trade(
        self, symbol: str, net_pnl_usd: float, exit_time_utc: datetime, interval_seconds: int
    ) -> None:
        self._trades += 1
        if net_pnl_usd < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._cooldown_until[symbol] = exit_time_utc + timedelta(
            seconds=self.config.cooldown_bars_after_exit * interval_seconds
        )

    def evaluate_batch(
        self, intents: list[OrderIntent], context: RiskContext
    ) -> tuple[RiskDecision, ...]:
        # Stable allocation: priority descending, symbol ascending, creation/intention sequence.
        ordered = sorted(intents, key=lambda item: (-item.priority, item.symbol, item.intent_id))
        decisions: list[RiskDecision] = []
        reserved_gross = context.portfolio.gross_exposure_usd
        reserved_cash = context.portfolio.cash_usd
        accepted_symbols = set(context.open_order_symbols)
        for intent in ordered:
            decision = self._evaluate_one(
                intent,
                context,
                reserved_gross=reserved_gross,
                reserved_cash=reserved_cash,
                accepted_symbols=accepted_symbols,
            )
            decisions.append(decision)
            if decision.accepted and decision.orders:
                parent = decision.orders[0]
                notional = parent.quantity * context.reference_prices[parent.symbol]
                reserved_gross += notional
                if parent.side is Side.BUY:
                    reserved_cash -= notional
                accepted_symbols.add(parent.symbol)
        return tuple(decisions)

    def _evaluate_one(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        reserved_gross: float,
        reserved_cash: float,
        accepted_symbols: set[str],
    ) -> RiskDecision:
        symbol = intent.symbol
        current_quantity = next(
            (position.quantity for position in context.portfolio.positions if position.symbol == symbol),
            0,
        )
        if intent.intent_type is not IntentType.ENTRY or intent.protective_exit:
            if current_quantity == 0:
                return self._reject(intent, RiskReason.NO_POSITION)
            quantity = min(abs(current_quantity), intent.requested_quantity or abs(current_quantity))
            order = self._make_parent(intent, quantity, context, reduce_only=True)
            return RiskDecision(
                intent=intent,
                accepted=True,
                reason=RiskReason.ACCEPTED,
                quantity=quantity,
                orders=(order,),
            )

        local_time = context.timestamp_utc.astimezone(_ET).time().replace(tzinfo=None)
        if not self.config.entry_start_time <= local_time <= self.config.latest_entry_time:
            return self._reject(intent, RiskReason.OUTSIDE_ENTRY_WINDOW)
        if self.config.direction == "long" and intent.side is Side.SELL:
            return self._reject(intent, RiskReason.DIRECTION_NOT_ALLOWED)
        if self.config.direction == "short" and intent.side is Side.BUY:
            return self._reject(intent, RiskReason.DIRECTION_NOT_ALLOWED)
        daily_pnl = context.portfolio.equity_usd - self._session_start_equity
        loss_limit = -self._session_start_equity * self.config.max_daily_loss_pct_of_starting_equity / 100.0
        if daily_pnl <= loss_limit:
            return self._reject(intent, RiskReason.DAILY_LOSS_LOCKOUT)
        if self._trades >= self.config.max_trades_per_session:
            return self._reject(intent, RiskReason.MAX_TRADES)
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            return self._reject(intent, RiskReason.MAX_CONSECUTIVE_LOSSES)
        if symbol in accepted_symbols:
            return self._reject(intent, RiskReason.DUPLICATE_ORDER)
        if current_quantity != 0:
            return self._reject(intent, RiskReason.DUPLICATE_ORDER)
        if len(context.portfolio.positions) >= self.config.max_concurrent_positions:
            return self._reject(intent, RiskReason.MAX_CONCURRENT_POSITIONS)
        cooldown = self._cooldown_until.get(symbol)
        if cooldown is not None and context.timestamp_utc <= cooldown:
            return self._reject(intent, RiskReason.COOLDOWN)
        reference = intent.entry_reference_price or context.reference_prices.get(symbol)
        if reference is None or reference <= 0:
            return self._reject(intent, RiskReason.INVALID_REFERENCE_PRICE)
        if intent.stop_loss_price is None:
            return self._reject(intent, RiskReason.INVALID_STOP)
        stop_distance = abs(reference - intent.stop_loss_price)
        if stop_distance <= 0:
            return self._reject(intent, RiskReason.INVALID_STOP)
        if intent.side is Side.BUY and intent.stop_loss_price >= reference:
            return self._reject(intent, RiskReason.INVALID_STOP)
        if intent.side is Side.SELL and intent.stop_loss_price <= reference:
            return self._reject(intent, RiskReason.INVALID_STOP)

        estimated_cost = self.costs.estimate_round_trip_per_share(reference)
        quantity = self._size(intent, context.portfolio, reference, stop_distance, estimated_cost)
        if quantity <= 0:
            return self._reject(intent, RiskReason.ZERO_QUANTITY)
        estimated_risk = quantity * (stop_distance + estimated_cost)
        original = quantity

        max_position = math.floor(
            context.portfolio.equity_usd * self.config.max_position_pct_of_equity / 100.0 / reference
        )
        quantity = min(quantity, max_position)
        if quantity <= 0:
            return self._reject(intent, RiskReason.POSITION_LIMIT)
        max_gross_dollars = (
            context.portfolio.equity_usd * self.config.max_gross_exposure_pct / 100.0
        )
        gross_capacity = max(0.0, max_gross_dollars - reserved_gross)
        quantity = min(quantity, math.floor(gross_capacity / reference))
        if quantity <= 0:
            return self._reject(intent, RiskReason.GROSS_EXPOSURE_LIMIT)
        if intent.side is Side.BUY and self.engine.max_leverage <= 1.0:
            quantity = min(quantity, math.floor(max(0.0, reserved_cash) / reference))
            if quantity <= 0:
                return self._reject(intent, RiskReason.CASH_LIMIT)
        volume = context.bar_volumes.get(symbol, 0)
        participation_cap = math.floor(
            volume * self.costs.config.volume_participation.max_pct_of_bar_volume / 100.0
        )
        if quantity > participation_cap:
            if self.costs.config.volume_participation.on_exceed == "reject":
                return self._reject(intent, RiskReason.VOLUME_PARTICIPATION_EXCEEDED)
            quantity = participation_cap
        if quantity <= 0:
            return self._reject(intent, RiskReason.VOLUME_PARTICIPATION_EXCEEDED)

        orders = self._build_orders(intent, quantity, context)
        reason = RiskReason.RESIZED if quantity < original else RiskReason.ACCEPTED
        estimated_risk = quantity * (stop_distance + estimated_cost)
        return RiskDecision(
            intent=intent,
            accepted=True,
            reason=reason,
            quantity=quantity,
            estimated_risk_usd=estimated_risk,
            orders=orders,
            details={"original_quantity": original, "final_quantity": quantity},
        )

    def _size(
        self,
        intent: OrderIntent,
        portfolio: PortfolioSnapshot,
        reference: float,
        stop_distance: float,
        estimated_cost: float,
    ) -> int:
        if intent.requested_quantity is not None:
            return intent.requested_quantity
        config = self.config.sizing
        model = intent.sizing_model or config.model
        if model == "risk_per_trade":
            percentage = config.risk_per_trade_pct_of_equity or 0.0
            budget = portfolio.equity_usd * percentage / 100.0
            return math.floor(budget / (stop_distance + estimated_cost))
        if model == "fixed_shares":
            return int(config.fixed_shares or 0)
        if model == "fixed_notional":
            return math.floor((config.fixed_notional_usd or 0.0) / reference)
        if model == "percent_equity":
            notional = portfolio.equity_usd * (config.percent_of_equity or 0.0) / 100.0
            return math.floor(notional / reference)
        return 0

    def _make_parent(
        self, intent: OrderIntent, quantity: int, context: RiskContext, *, reduce_only: bool
    ) -> Order:
        delay = timedelta(seconds=context.interval_seconds * self.engine.additional_entry_delay_bars)
        order_id = self.ids.next_order()
        return Order(
            order_id=order_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=quantity,
            status=OrderStatus.ACCEPTED,
            created_at_utc=intent.signal_time_utc,
            eligible_from_utc=intent.signal_time_utc + delay,
            expires_at_utc=intent.expires_at_utc or context.session_close_utc,
            limit_price=intent.limit_price,
            stop_price=intent.stop_trigger_price,
            bracket_stop_price=intent.stop_loss_price,
            bracket_target_price=intent.take_profit_price,
            priority=intent.priority,
            creation_sequence=order_id,
            reduce_only=reduce_only,
            reason_code="RISK_ACCEPTED",
            estimated_risk_usd=None,
        )

    def _build_orders(
        self, intent: OrderIntent, quantity: int, context: RiskContext
    ) -> tuple[Order, ...]:
        parent = self._make_parent(intent, quantity, context, reduce_only=False)
        orders: list[Order] = [parent]
        child_side = intent.side.opposite
        if intent.stop_loss_price is not None:
            child_id = self.ids.next_order()
            orders.append(
                Order(
                    order_id=child_id,
                    intent_id=intent.intent_id,
                    parent_order_id=parent.order_id,
                    strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version,
                    symbol=intent.symbol,
                    side=child_side,
                    order_type=OrderType.STOP,
                    quantity=quantity,
                    status=OrderStatus.CREATED,
                    created_at_utc=intent.signal_time_utc,
                    eligible_from_utc=parent.eligible_from_utc,
                    expires_at_utc=context.session_close_utc,
                    stop_price=intent.stop_loss_price,
                    priority=intent.priority + 100,
                    creation_sequence=child_id,
                    reduce_only=True,
                    reason_code="PROTECTIVE_STOP",
                    tags=("protective", "stop"),
                )
            )
        if intent.take_profit_price is not None:
            child_id = self.ids.next_order()
            orders.append(
                Order(
                    order_id=child_id,
                    intent_id=intent.intent_id,
                    parent_order_id=parent.order_id,
                    strategy_id=intent.strategy_id,
                    strategy_version=intent.strategy_version,
                    symbol=intent.symbol,
                    side=child_side,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    status=OrderStatus.CREATED,
                    created_at_utc=intent.signal_time_utc,
                    eligible_from_utc=parent.eligible_from_utc,
                    expires_at_utc=context.session_close_utc,
                    limit_price=intent.take_profit_price,
                    priority=intent.priority + 90,
                    creation_sequence=child_id,
                    reduce_only=True,
                    reason_code="PROFIT_TARGET",
                    tags=("protective", "target"),
                )
            )
        return tuple(orders)

    @staticmethod
    def _reject(intent: OrderIntent, reason: RiskReason) -> RiskDecision:
        return RiskDecision(intent=intent, accepted=False, reason=reason)
