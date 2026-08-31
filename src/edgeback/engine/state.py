from __future__ import annotations

from dataclasses import dataclass, field

from edgeback.domain import (
    EquityPoint,
    Fill,
    Order,
    OrderEvent,
    OrderIntent,
    PortfolioSnapshot,
    RunStatus,
    Trade,
    WarningEvent,
)
from edgeback.risk import RiskDecision


@dataclass(slots=True)
class BacktestResult:
    status: RunStatus
    intents: list[OrderIntent] = field(default_factory=list)
    risk_decisions: list[RiskDecision] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    order_events: list[OrderEvent] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    equity: list[EquityPoint] = field(default_factory=list)
    warnings: list[WarningEvent] = field(default_factory=list)
    final_snapshot: PortfolioSnapshot | None = None
    reconciliation: dict[str, float | bool] = field(default_factory=dict)
    strategy_states: dict[str, dict[str, object]] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    traceback_text: str | None = None
