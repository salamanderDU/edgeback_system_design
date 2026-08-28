from pydantic import Field

from edgeback.config.models import BaseStrictModel


class Position(BaseStrictModel):
    """
    Snapshot of a current holding.
    """

    symbol: str
    shares: int = 0
    average_price: float = Field(default=0.0, ge=0.0)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0


class PortfolioSnapshot(BaseStrictModel):
    """
    Snapshot of the entire portfolio equity and exposure.
    """

    cash: float
    equity: float
    gross_exposure: float
    net_exposure: float
