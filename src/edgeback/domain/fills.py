from datetime import datetime
from typing import Literal

from pydantic import Field

from edgeback.config.models import BaseStrictModel


class Fill(BaseStrictModel):
    """
    An execution event representing a trade happening securely at an exact timestamp.
    """

    id: str
    order_id: str
    symbol: str
    timestamp_utc: datetime

    direction: Literal["long", "short"]
    action: Literal["buy", "sell"]
    shares: int = Field(gt=0)
    fill_price: float = Field(gt=0.0)

    # Decomposed cost models
    commission_usd: float = Field(ge=0.0)
    slippage_usd: float = Field(ge=0.0)
    spread_usd: float = Field(ge=0.0)

    reason: str = "market_fill"
