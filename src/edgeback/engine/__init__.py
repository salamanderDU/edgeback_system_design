"""Deterministic event engines: single-symbol (T440) and multi-symbol (T450)."""

from edgeback.engine.allocation import (
    AllocationContext,
    IntentAllocator,
    PriorityThenSymbolAllocator,
    build_allocator,
)
from edgeback.engine.event_loop import (
    EngineError,
    EngineRunResult,
    EquityPoint,
    SingleSymbolEventEngine,
    run_single_symbol_backtest,
)
from edgeback.engine.multi_symbol import (
    MultiSymbolEventEngine,
    MultiSymbolRunResult,
    run_multi_symbol_backtest,
)

__all__ = [
    "AllocationContext",
    "EngineError",
    "EngineRunResult",
    "EquityPoint",
    "IntentAllocator",
    "MultiSymbolEventEngine",
    "MultiSymbolRunResult",
    "PriorityThenSymbolAllocator",
    "SingleSymbolEventEngine",
    "build_allocator",
    "run_multi_symbol_backtest",
    "run_single_symbol_backtest",
]
