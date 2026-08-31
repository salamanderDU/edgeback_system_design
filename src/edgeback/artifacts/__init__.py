"""EdgeBack run artifacts.

T500 canonical result tables (deterministic Parquet builders from engine
results). The atomic run writer (T520), SQLite registry (T530), and HTML
report (T540) are added on top of these builders in later tasks.
"""

from edgeback.artifacts.tables import (
    ClosedTrade,
    RunResultTables,
    build_decisions_frame,
    build_equity_frame,
    build_fills_frame,
    build_intents_frame,
    build_order_events_frame,
    build_orders_frame,
    build_trades_frame,
    build_warnings_frame,
    trades_from_fills,
    write_run_tables,
)

__all__ = [
    "ClosedTrade",
    "RunResultTables",
    "build_decisions_frame",
    "build_equity_frame",
    "build_fills_frame",
    "build_intents_frame",
    "build_order_events_frame",
    "build_orders_frame",
    "build_trades_frame",
    "build_warnings_frame",
    "trades_from_fills",
    "write_run_tables",
]
