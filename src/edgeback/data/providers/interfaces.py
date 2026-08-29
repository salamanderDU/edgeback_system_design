from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from edgeback.config.models import BaseStrictModel


class BarRequest(BaseStrictModel):
    symbols: list[str]
    interval_seconds: int
    start_utc: datetime
    end_utc: datetime
    include_pre_market: bool = False
    include_post_market: bool = False
    feed: str | None = None
    adjustment_mode: str = "split_adjusted"


class RawBarBatch(BaseStrictModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    data: Any  # pd.DataFrame
    provider_id: str
    source_feed: str
    fetched_at_utc: datetime = Field(default_factory=lambda: datetime.now())



class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @abstractmethod
    def fetch_bars(self, request: BarRequest) -> RawBarBatch:
        pass
