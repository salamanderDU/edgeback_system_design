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

    # Size hint. Strategy can request shares, or risk model will determine sizing
    requested_shares: int | None = Field(default=None, gt=0)

    # Tag for user tracking
    tag: str = ""


class Order(BaseStrictModel):
    """
    An approved order that the execution engine will process against market bars.
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
