from __future__ import annotations

from enum import StrEnum


class SessionType(StrEnum):
    REGULAR = "regular"
    PRE = "pre"
    POST = "post"
    OVERNIGHT = "overnight"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class IntentType(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"
    REDUCE = "reduce"
    CANCEL = "cancel"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    WORKING = "working"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class TimeInForce(StrEnum):
    DAY = "day"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
