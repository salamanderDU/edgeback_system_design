"""
Risk manager (T430).

Implements ``docs/04_BACKTEST_ENGINE.md`` §8-9 (and FR-007): strategies emit
intents; the risk manager sizes or rejects them before the broker sees an
order. Every decision carries a machine-readable reason code.

Evaluation pipeline (docs/04 §8):
1. trading-session / entry-time eligibility;
2. direction permission;
3. daily loss / trade / consecutive-loss lockouts and cooldown;
4. stop-distance validity (required for risk-per-trade sizing);
5. position sizing (risk_per_trade / fixed_shares / fixed_notional /
   percent_equity);
6. per-position limit;
7. gross/net exposure and cash/margin;
8. volume participation;
9. duplicate/conflicting order checks.

Protective exits (``intent.protective_exit = True``) bypass lockouts and
sizing so bracket children are never blocked by daily controls (docs/04 §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from edgeback.config.models import ExecutionConfig, RiskConfig, VolumeParticipationConfig
from edgeback.domain.orders import Order, OrderIntent
from edgeback.domain.positions import Position
from edgeback.portfolio.accounting import round_money

__all__ = [
    "RiskManager",
    "RiskContext",
    "RiskDecision",
    "RiskReason",
    "risk_manager_from_config",
]


class RiskReason(StrEnum):
    """Machine-readable reason codes for accepted/rejected intents."""

    OK = "OK"
    ENTRY_WINDOW = "ENTRY_WINDOW"
    DIRECTION_FORBIDDEN = "DIRECTION_FORBIDDEN"
    DAILY_LOSS_LOCKOUT = "DAILY_LOSS_LOCKOUT"
    MAX_TRADES_REACHED = "MAX_TRADES_REACHED"
    MAX_CONSECUTIVE_LOSSES = "MAX_CONSECUTIVE_LOSSES"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    INVALID_STOP = "INVALID_STOP"
    SIZING_POSITIVE_SHARES_REQUIRED = "SIZING_POSITIVE_SHARES_REQUIRED"
    PER_POSITION_LIMIT = "PER_POSITION_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    CASH_LIMIT = "CASH_LIMIT"
    VOLUME_PARTICIPATION_EXCEEDED = "VOLUME_PARTICIPATION_EXCEEDED"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"


@dataclass(frozen=True)
class RiskContext:
    """
    Read-only portfolio/session state supplied by the engine at evaluation time.

    Parameters
    ----------
    equity
        Current portfolio equity.
    cash
        Current cash balance.
    positions
        Open positions keyed by symbol (signed ``shares``).
    gross_exposure
        Current gross exposure in USD.
    reference_prices
        Reference execution price per symbol used for sizing/caps. A symbol
        missing from the map cannot be sized (no hard-coded prices).
    session_pnl
        Realized plus mark-to-market P&L for the current session (authoritative
        daily-loss input supplied by the engine).
    current_time_utc
        Engine clock (UTC, timezone-aware).
    session_date
        Exchange-local session date.
    bar_volume
        Current bar volume (for participation cap); ``None`` disables the cap.
    estimated_cost_per_share
        Estimated round-trip cost per share used by risk-per-trade sizing.
    start_equity
        Equity at session start (daily-loss baseline); defaults to ``equity``.
    """

    equity: float
    cash: float
    positions: dict[str, Position]
    gross_exposure: float
    reference_prices: dict[str, float]
    session_pnl: float = 0.0
    current_time_utc: datetime | None = None
    session_date: date | None = None
    bar_volume: int | None = None
    estimated_cost_per_share: float = 0.0
    start_equity: float | None = None


@dataclass(frozen=True)
class RiskDecision:
    """Result of evaluating one intent."""

    intent: OrderIntent
    accepted: bool
    reason: RiskReason
    message: str
    sized_shares: int | None = None
    order: Order | None = None


class RiskManager:
    """
    Deterministic risk evaluator.

    Parameters
    ----------
    config
        Resolved risk configuration.
    volume_participation
        Optional participation config (from the execution block) used by the
        volume-participation rule.
    timezone
        Exchange-local timezone name (default ``America/New_York``).
    """

    def __init__(
        self,
        config: RiskConfig,
        volume_participation: VolumeParticipationConfig | None = None,
        timezone: str = "America/New_York",
    ) -> None:
        self._config = config
        self._volume_participation = volume_participation
        self._tz = ZoneInfo(timezone)
        self.reset_session()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def reset_session(self) -> None:
        """Reset all per-session counters (called at every session start)."""
        self._start_equity: float | None = None
        self._trades_taken = 0
        self._consecutive_losses = 0
        self._bars_since_exit: int | None = None
        self._pending_entry_orders: set[tuple[str, str, str]] = set()

    def on_session_start(self, start_equity: float) -> None:
        """Begin a new session with the given starting equity baseline."""
        self.reset_session()
        self._start_equity = round_money(start_equity)

    def on_bar(self) -> None:
        """Advance the cooldown counter by one bar."""
        if self._bars_since_exit is not None:
            self._bars_since_exit += 1

    def record_trade(self, realized_pnl: float) -> None:
        """
        Record a completed trade for the session counters.

        The engine calls this when a position closes (protective child or
        forced liquidation). ``realized_pnl`` is net of costs.
        """
        self._trades_taken += 1
        self._bars_since_exit = 0
        if realized_pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, intent: OrderIntent, ctx: RiskContext) -> RiskDecision:
        """Size or reject a single intent."""
        now_utc = ctx.current_time_utc or datetime(2025, 1, 1, tzinfo=UTC)
        start_equity = ctx.start_equity if ctx.start_equity is not None else ctx.equity

        # --- Protective exits bypass lockouts and sizing entirely.
        if intent.protective_exit:
            return self._accept_protective(intent)

        # 1. Entry-time window.
        local_time = now_utc.astimezone(self._tz).time()
        if self._outside_entry_window(local_time):
            return self._reject(intent, RiskReason.ENTRY_WINDOW, "outside entry window")

        # 2. Direction permission.
        if intent.direction not in ("long", "short"):
            return self._reject(
                intent, RiskReason.DIRECTION_FORBIDDEN, "flat intent is not an entry"
            )
        if self._config.direction == "long" and intent.direction != "long":
            return self._reject(intent, RiskReason.DIRECTION_FORBIDDEN, "short disabled")
        if self._config.direction == "short" and intent.direction != "short":
            return self._reject(intent, RiskReason.DIRECTION_FORBIDDEN, "long disabled")

        # 3. Daily lockouts / trade counts / cooldown.
        max_daily_loss = round_money(
            start_equity * self._config.max_daily_loss_pct_of_starting_equity / 100.0
        )
        if ctx.session_pnl <= -max_daily_loss:
            return self._reject(intent, RiskReason.DAILY_LOSS_LOCKOUT, "daily loss limit reached")

        if self._trades_taken >= self._config.max_trades_per_session:
            return self._reject(intent, RiskReason.MAX_TRADES_REACHED, "max trades per session")

        if (
            self._config.max_consecutive_losses > 0
            and self._consecutive_losses >= self._config.max_consecutive_losses
        ):
            return self._reject(intent, RiskReason.MAX_CONSECUTIVE_LOSSES, "max consecutive losses")

        if self._config.cooldown_bars_after_exit > 0 and self._bars_since_exit is not None:
            if self._bars_since_exit < self._config.cooldown_bars_after_exit:
                return self._reject(
                    intent,
                    RiskReason.COOLDOWN_ACTIVE,
                    f"cooldown {self._bars_since_exit}/"
                    f"{self._config.cooldown_bars_after_exit} bars",
                )

        # 3b. Duplicate/conflicting order check.
        key = (intent.symbol, intent.direction, intent.intent_type)
        if key in self._pending_entry_orders:
            return self._reject(intent, RiskReason.DUPLICATE_ORDER, "duplicate entry intent")

        # 4. Max concurrent positions.
        if self._open_position_count(ctx.positions) >= self._config.max_concurrent_positions:
            return self._reject(
                intent, RiskReason.MAX_POSITIONS_REACHED, "max concurrent positions"
            )

        reference_price = ctx.reference_prices.get(intent.symbol)
        if reference_price is None or reference_price <= 0:
            return self._reject(
                intent,
                RiskReason.SIZING_POSITIVE_SHARES_REQUIRED,
                "no reference price for sizing",
            )

        # 5. Stop-distance validity for risk-per-trade sizing.
        if self._config.sizing.model == "risk_per_trade" and intent.stop_price is None:
            return self._reject(intent, RiskReason.INVALID_STOP, "risk_per_trade requires a stop")

        # 6. Sizing.
        sized = self._size(intent, ctx, reference_price)
        if sized <= 0:
            return self._reject(
                intent, RiskReason.SIZING_POSITIVE_SHARES_REQUIRED, "size rounds to zero"
            )

        # 7. Per-position limit.
        max_position_shares = self._max_position_shares(ctx.equity, reference_price)
        if max_position_shares is not None and sized > max_position_shares:
            sized = max_position_shares
            if sized <= 0:
                return self._reject(
                    intent, RiskReason.PER_POSITION_LIMIT, "per-position cap floors to zero"
                )

        # 8. Volume participation.
        if self._volume_participation is not None and ctx.bar_volume is not None:
            capped = self._apply_participation_cap(sized, ctx.bar_volume)
            if capped <= 0:
                return self._reject(
                    intent,
                    RiskReason.VOLUME_PARTICIPATION_EXCEEDED,
                    "exceeds configured participation cap",
                )
            sized = capped

        # 9. Exposure and cash.
        notional = sized * reference_price
        max_gross = start_equity * self._config.max_gross_exposure_pct / 100.0
        if ctx.gross_exposure + notional > max_gross:
            return self._reject(
                intent, RiskReason.GROSS_EXPOSURE_LIMIT, "gross exposure cap exceeded"
            )
        if ctx.cash < notional:
            return self._reject(intent, RiskReason.CASH_LIMIT, "insufficient cash for entry")

        order = self._build_entry_order(intent, sized)
        self._pending_entry_orders.add(key)
        return RiskDecision(
            intent=intent,
            accepted=True,
            reason=RiskReason.OK,
            message="accepted",
            sized_shares=sized,
            order=order,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_entry_order(self, intent: OrderIntent, shares: int) -> Order:
        order_seq = len(self._pending_entry_orders) + 1
        # ADR-012: an intent with both a stop and a take-profit becomes a
        # bracket entry; the T420 broker activates the protective children.
        has_bracket = intent.stop_price is not None and intent.take_profit_price is not None
        if has_bracket:
            order_type: Literal["market", "limit", "stop", "bracket"] = "bracket"
        elif intent.intent_type == "limit":
            order_type = "limit"
        else:
            order_type = "market"
        return Order(
            id=f"{intent.symbol}-{intent.direction}-{intent.intent_type}-{order_seq}",
            symbol=intent.symbol,
            direction="long" if intent.direction == "long" else "short",
            order_type=order_type,
            shares=shares,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            stop_loss_price=intent.stop_price if has_bracket else None,
            take_profit_price=intent.take_profit_price if has_bracket else None,
            eligible_from_utc=None,
            status="pending",
        )

    def _accept_protective(self, intent: OrderIntent) -> RiskDecision:
        """Protective exits always pass through (no sizing/lockouts)."""
        return RiskDecision(
            intent=intent,
            accepted=True,
            reason=RiskReason.OK,
            message="protective exit accepted",
        )

    @staticmethod
    def _open_position_count(positions: dict[str, Position]) -> int:
        return sum(1 for p in positions.values() if p.shares != 0)

    def _reject(self, intent: OrderIntent, reason: RiskReason, message: str) -> RiskDecision:
        return RiskDecision(intent=intent, accepted=False, reason=reason, message=message)

    def _outside_entry_window(self, local_time: time) -> bool:
        start_h, start_m = map(int, self._config.entry_start_time.split(":"))
        latest_h, latest_m = map(int, self._config.latest_entry_time.split(":"))
        start = time(start_h, start_m)
        latest = time(latest_h, latest_m)
        return not (start <= local_time <= latest)

    def _size(self, intent: OrderIntent, ctx: RiskContext, price: float) -> int:
        sizing = self._config.sizing
        model = sizing.model
        if model == "fixed_shares":
            assert sizing.fixed_shares is not None
            return sizing.fixed_shares
        if model == "fixed_notional":
            assert sizing.fixed_notional_usd is not None
            return max(0, int(sizing.fixed_notional_usd // price))
        if model == "percent_equity":
            assert sizing.percent_equity_pct is not None
            notional = ctx.equity * sizing.percent_equity_pct / 100.0
            return max(0, int(notional // price))
        # risk_per_trade (docs/04 §8)
        assert sizing.risk_per_trade_pct_of_equity is not None
        assert intent.stop_price is not None
        risk_per_share = abs(price - intent.stop_price) + ctx.estimated_cost_per_share
        if risk_per_share <= 0:
            return 0
        risk_budget = ctx.equity * sizing.risk_per_trade_pct_of_equity / 100.0
        return max(0, int(risk_budget // risk_per_share))

    def _max_position_shares(self, equity: float, price: float) -> int | None:
        if price <= 0:
            return None
        return max(0, int(equity * self._config.max_position_pct_of_equity / 100.0 // price))

    def _apply_participation_cap(self, shares: int, bar_volume: int) -> int:
        if self._volume_participation is None or bar_volume <= 0:
            return shares
        cap_shares = int(bar_volume * self._volume_participation.max_pct_of_bar_volume / 100.0)
        if shares <= cap_shares:
            return shares
        if self._volume_participation.on_exceed == "cap":
            return cap_shares
        return 0  # reject


def risk_manager_from_config(
    config: RiskConfig,
    execution: ExecutionConfig | None = None,
) -> RiskManager:
    """Build a risk manager from resolved configuration."""
    participation = execution.volume_participation if execution is not None else None
    return RiskManager(config=config, volume_participation=participation)
