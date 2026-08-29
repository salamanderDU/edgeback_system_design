from datetime import datetime
from typing import Literal

from pydantic import Field

from edgeback.config.models import BaseStrictModel


class OrderIntent(BaseStrictModel):
    """
    A signal request created by a strategy, before risk evaluation and broker conversion.
    """

    symbol: str = Field(pattern="^[A-Z0-9.\\-]+$")
    direction: Literal["long", "short", "flat"]
    # For enter or exit? Let's use order types closely matching standard orders
    # or just intentions. We will adopt Standard order matching semantics as per docs:
    intent_type: Literal["market", "limit", "stop"]

    # Optional parameters for non-market
    limit_price: float | None = Field(default=None, gt=0.0)
    stop_price: float | None = Field(default=None, gt=0.0)
    # Optional target for the protective bracket (docs/05 §7, ADR-012).
    # When both stop_price and take_profit_price are set, the risk manager
    # builds a bracket order with stop-loss and take-profit children.
    take_profit_price: float | None = Field(default=None, gt=0.0)

    # Size hint. Strategy can request shares, or risk model will determine sizing
    requested_shares: int | None = Field(default=None, gt=0)

    # Tag for user tracking
    tag: str = ""

    # Risk-manager flag: protective exits (bracket children / forced liquidation)
    # bypass daily lockouts and sizing (docs/04 §9).
    protective_exit: bool = False


class Order(BaseStrictModel):
    """
    An approved order that the execution engine will process against market bars.

    Timeline/ordering fields added by T420 are optional and defaulted so the
    model stays backward compatible. ``eligible_from_utc`` is the earliest time
    at which the order may fill (next-bar semantics); ``expires_at_utc`` caps
    its working life; ``creation_sequence``, ``priority``, and ``parent_order_id``
    support deterministic evaluation and bracket children.
    """

    id: str
    symbol: str
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit", "stop", "bracket"]
    shares: int = Field(gt=0)

    limit_price: float | None = None
    stop_price: float | None = None

    # Bracket order specific targets
    take_profit_price: float | None = None
    stop_loss_price: float | None = None

    status: Literal["pending", "open", "filled", "cancelled", "rejected"] = "pending"
    reason: str = ""

    eligible_from_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    parent_order_id: str | None = None
    priority: int = 0
    creation_sequence: int = 0


class OrderEvent(BaseStrictModel):
    """
    An event representing a change in an Order's state (e.g. filled, cancelled, rejected).
    """

    order: Order
    event_type: Literal["submitted", "accepted", "filled", "partial_fill", "cancelled", "rejected"]
    timestamp_utc: str | None = None
    reason: str = ""
