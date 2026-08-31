"""Non-CI throughput and memory smoke benchmark for the reference event engine."""

from __future__ import annotations

import argparse
import time
import tracemalloc
from pathlib import Path

from edgeback.config import resolve_config
from edgeback.data.fixtures import generate_fixture_bars
from edgeback.engine import run_backtest

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=250)
    parser.add_argument("--symbols", type=int, default=10)
    args = parser.parse_args()
    names = tuple(f"FIX{index:03d}" for index in range(args.symbols))
    config = resolve_config(ROOT / "configs/example_backtest.yaml", symbols=list(names))
    bars = generate_fixture_bars(
        symbols=names,
        interval_seconds=config.data.interval_seconds,
        session_count=args.sessions,
    )
    tracemalloc.start()
    started = time.perf_counter()
    result = run_backtest(config, bars)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        {
            "status": result.status.value,
            "bar_events": len(bars),
            "seconds": round(elapsed, 4),
            "events_per_second": round(len(bars) / elapsed, 2) if elapsed else None,
            "peak_memory_mb": round(peak / 1024 / 1024, 2),
            "trades": len(result.trades),
        }
    )
    return 0 if result.status.value == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
