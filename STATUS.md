# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** M5_IN_PROGRESS
**Current milestone:** M5 — Metrics, artifacts, registry, and reports (IN_PROGRESS)
**Current task:** T500 — Canonical result tables
**Current task status:** IN_PROGRESS (T500 marked IN_PROGRESS in TASK.md; implementation started)
**Working tree:** M4 complete. All gates green at handoff: 185 tests pass, Ruff lint/format pass, mypy clean (49 source files). No new code beyond TASK.md/STATUS.md markers.

## Current objective

**T500 — Canonical result tables** (M5). T500 depends on T440 (DONE) and must implement the intents/orders/fills/trades/equity Parquet artifact tables with complete linkage, stable schemas, and reason/cost fields per `docs/07_CLI_CONFIG_AND_ARTIFACTS.md` §8-11 and `docs/04_BACKTEST_ENGINE.md` §14. The M4 engines already produce all tuples needed (intents, decisions, orders, fills, broker events, warnings, equity curve, reconciliation); T500 turns them into canonical Parquet tables.

## In progress this session

- **T500 IN_PROGRESS — canonical result tables (new module `src/edgeback/artifacts/tables.py`).**
  - Task marked IN_PROGRESS in `TASK.md`; milestone summary updated to M5 IN_PROGRESS.
  - Implement `parquet_intents`, `parquet_decisions`, `parquet_orders`, `parquet_fills`, `parquet_trades`, `parquet_equity`, and `parquet_warnings` writers with stable Arrow schemas.
  - Complete linkage: every order links to its originating intent (via creation/direction/symbol), fills link to orders, trades link entry/exit fills and orders, per-bar equity snapshots.
  - Reason codes (RiskReason) and cost decomposition fields (spread/slippage/commission/effective price) present per docs/07 §10 and docs/04 §6/§14.
  - Trades table: signed realized P&L at base prices, entry/exit fill order ids, side, symbol, entry/exit timestamps, holding seconds, tags (protective/forced), costs.
  - Tests: schema stability (column names/arrow types), linkage invariants (`fill.order_id` exists in orders, trades reconcile to realized P&L via `project_fills`), deterministic rerun produces identical tables, both engine result types accepted, failure/empty inputs handled.
  - Deferred to T520 (run writer): directory layout, atomic write, checksums, run metadata JSON.

## Files changed

- `TASK.md` (title header milestone → M5; milestone summary M5 IN_PROGRESS; T500 detail → IN_PROGRESS with evidence line)
- `STATUS.md` (this checkpooint)

## Validation (exact commands)

- Baseline at handoff: `.venv/bin/python -m pytest` → 185 passed; `.venv/bin/ruff check .` clean; `.venv/bin/ruff format --check .` 92 files formatted; `.venv/bin/python -m mypy src` → no issues in 49 source files.
- T500 checks pending after implementation.

## Blockers

- None.

## Notes for next session

- T500 will add `src/edgeback/artifacts/tables.py` plus `tests/unit/test_artifact_tables.py`.
- `.env.example` exists at repo root (confirmed).
- `pyproject.toml` still has the unused `module = ['tests.*']` mypy section (pre-existing; clean-up optional).
- mypy's `.venv/bin/mypy` executable has a stale shebang; use `.venv/bin/python -m mypy src`.
- T520 (atomic run writer) will consume the T500 table writers; T510 (metrics) consumes fills/trades/equity tables.

## Exact next actions

1. Write `src/edgeback/artifacts/tables.py` (canonical Parquet table writers + stable Arrow schemas).
2. Add `tests/unit/test_artifact_tables.py` (schema stability, linkage invariants, determinism, both engine results, edge cases).
3. Run `pytest`, `ruff check .`, `ruff format --check .`, `mypy src`; record evidence; mark T500 DONE.

## Resume note

Safe to resume. T500 IN_PROGRESS with exact next action documented. Baseline gates green at session start.