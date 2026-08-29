# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** T340_COMPLETE
**Current milestone:** M4 — Event engine, execution, portfolio, and risk
**Current task:** T400 — Portfolio ledger
**Current task status:** TODO
**Working tree:** T340 complete. M0, M1, M2, and M3 are all complete. All 64 unit tests pass cleanly, Ruff lint/format checks pass, and mypy type checks pass with 0 errors.

## Current objective

T400: Implement portfolio ledger and accounting invariants (`src/edgeback/portfolio/ledger.py` and `src/edgeback/portfolio/accounting.py`).

## Completed in the latest session

- Restored data layer modules (`schema.py`, `manifest.py`, `repository.py`, and local providers) and fixed root-scoped `.gitignore` pattern.
- Implemented `src/edgeback/strategy/services.py` containing:
  - `discover_strategies()` for safe discovery and conflict detection of registered strategies from the trusted `strategies/` package.
  - `list_strategies_service()` returning deterministically sorted `StrategySummary` objects.
  - `describe_strategy_service(strategy_id)` returning `StrategyDetail` with full metadata and Pydantic JSON parameter schema.
- Added `StrategySummary` and `StrategyDetail` models in `src/edgeback/strategy/models.py`.
- Registered `OpeningRangeBreakout` with `@register_strategy`.
- Implemented comprehensive unit tests in `tests/unit/test_strategy_services.py` testing list sorting, parameter schema extraction, default parameter capture, missing strategy handling, and duplicate strategy ID conflict detection.
- Passed full test suite (64/64 tests) and all quality gates (`ruff check`, `ruff format --check`, `mypy src`).
- Marked T340 as DONE in `TASK.md` and updated milestone summary (M3 complete).

## Implementation completed

- Configurations models `src/edgeback/config/models.py`
- Configuration loader `src/edgeback/config/loader.py`
- Domain schemas `src/edgeback/domain/bars.py`, `fills.py`, `positions.py`, `orders.py`
- Reproducibility artifacts `src/edgeback/artifacts/reproducibility.py`
- Calendar abstractions `src/edgeback/calendar/interfaces.py`, `src/edgeback/calendar/xnys.py`
- Local Data Schema models `src/edgeback/data/schema.py`
- Local Provider mapping logic `src/edgeback/data/providers/interfaces.py`, `local.py`
- Repository interactions `src/edgeback/data/manifest.py`, `repository.py`
- Core Data Fixtures `tests/fixtures/synthetic.py`, `test_fixtures.py`
- Strategy contract `src/edgeback/strategy/models.py`, `context.py`, `base.py`, `registry.py`
- Strategy services `src/edgeback/strategy/services.py`
- Causal context `src/edgeback/strategy/history.py`
- Feature helpers `src/edgeback/features/range.py`, `indicators.py`
- Opening Range Breakout Strategy `strategies/opening_range_breakout.py`
- ORB Strategy Tests `tests/unit/test_strategy_orb.py`
- Strategy Services Tests `tests/unit/test_strategy_services.py`

## Files changed in latest session

- `.gitignore`
- `src/edgeback/data/__init__.py`
- `src/edgeback/data/schema.py`
- `src/edgeback/data/manifest.py`
- `src/edgeback/data/repository.py`
- `src/edgeback/data/providers/__init__.py`
- `src/edgeback/data/providers/interfaces.py`
- `src/edgeback/data/providers/local.py`
- `src/edgeback/strategy/__init__.py`
- `src/edgeback/strategy/base.py`
- `src/edgeback/strategy/models.py`
- `src/edgeback/strategy/registry.py`
- `src/edgeback/strategy/services.py`
- `src/edgeback/strategy/history.py`
- `src/edgeback/artifacts/reproducibility.py`
- `strategies/opening_range_breakout.py`
- `tests/unit/test_strategy_services.py`
- `TASK.md`
- `STATUS.md`

## Validation performed

- `python -m pytest` (64 passed in 1.74s)
- `python -m ruff check .` (All checks passed)
- `python -m ruff format --check .` (77 files already formatted)
- `python -m mypy src` (Success: no issues found in 41 source files)

## Known blockers

- None

## Exact next actions

1. Start T400: Implement portfolio ledger and accounting invariants (`src/edgeback/portfolio/ledger.py` and `src/edgeback/portfolio/accounting.py`).
2. Mark T400 as `IN_PROGRESS` in `TASK.md` and update `STATUS.md` before editing files.
3. Implement portfolio ledger handling long/short positions, cash tracking, mark-to-market valuations, realized/unrealized P&L, and equity snapshots.
4. Add unit and invariant tests in `tests/unit/test_portfolio.py`.

## Resume note

Safe to resume. M3 is completed. The next task to pick up is `T400` in milestone `M4`.
