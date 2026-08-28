from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from edgeback.domain.bars import Bar
from edgeback.domain.orders import OrderIntent


class StrategyContext(ABC):
    """
    Read-only causal context provided to strategies.
    Strategies use this to get information and create intents.
    """

    @property
    @abstractmethod
    def engine_time_utc(self) -> datetime:
        """Current engine time in UTC."""
        pass

    @abstractmethod
    def history(self, symbol: str, bars: int) -> list[Bar]:
        """
        Get causal historical bars up to current time for the given symbol.
        Returns a list of completed Bars.
        """
        pass

    @abstractmethod
    def create_intent(self, **kwargs: Any) -> OrderIntent:
        """
        Factory method to create an OrderIntent.
        """
        pass
