from typing import Literal

from pydantic import Field

from edgeback.config.models import BaseStrictModel


class StrategyMetadata(BaseStrictModel):
    """
    Metadata for a registered strategy.
    """

    strategy_id: str
    version: str
    name: str = ""
    description: str = ""
    scope: Literal["per_symbol", "portfolio"] = "per_symbol"
    warmup_bars: int = Field(ge=0, default=0)
    required_fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")
    research_status: Literal["hypothesis", "experimental", "validated_for_dataset"] = (
        "hypothesis"
    )
    known_limitations: list[str] = Field(default_factory=list)
