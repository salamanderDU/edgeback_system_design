from __future__ import annotations


class IdAllocator:
    """Run-scoped deterministic monotonic IDs."""

    def __init__(self) -> None:
        self._intent = 0
        self._order = 0
        self._fill = 0
        self._event = 0
        self._trade = 0
        self._warning = 0

    def next_intent(self) -> int:
        self._intent += 1
        return self._intent

    def next_order(self) -> int:
        self._order += 1
        return self._order

    def next_fill(self) -> int:
        self._fill += 1
        return self._fill

    def next_event(self) -> int:
        self._event += 1
        return self._event

    def next_trade(self) -> int:
        self._trade += 1
        return self._trade

    def next_warning(self) -> int:
        self._warning += 1
        return self._warning
