# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29 (Asia/Bangkok)
**Project state:** T310_COMPLETE
**Current milestone:** M3 — Strategy API, features, execution, and engine core
**Current task:** T320 — Implement pure feature helpers
**Current task status:** TODO
**Working tree:** T310 completed. Causal history context successfully guards against future bars and mutated state.

## Current objective

Begin T320: Implement pure feature helpers needed by ORB (Opening Range Breakout).

## Completed in the latest design session

- Created `CausalStrategyContext` in `src/edgeback/strategy/history.py`.
- Wrote test cases in `tests/unit/test_history.py` to ensure only past/current bars are returned.
- Ensured mutation of history returns does not affect context memory and underlying Pydantic models are frozen.
- Marked T310 as DONE in TASK.md.

## Implementation completed

- Configurations models `models.py`
- Configuration loader `loader.py`
- Domain schemas `bars.py`, `fills.py`, `positions.py`, `orders.py`
- Reproducibility artifacts `reproducibility.py`
- Calendar abstractions `calendar/interfaces.py`, `calendar/xnys.py`
- Local Data Schema models `schema.py`
- Local Provider mapping logic `providers/interfaces.py`, `providers/local.py`
- Repository interactions `manifest.py`, `repository.py`
- Core Data Fixtures `synthetic.py`, `test_fixtures.py`
- Strategy contract `models.py`, `context.py`, `base.py`, `registry.py`
- Causal context `history.py`

## Files expected to be created next

- `src/edgeback/features/` (directory for pure indicator helpers)
- `src/edgeback/features/range.py` (or similar)
- `tests/unit/test_features.py`

## Validation performed

- `python -m pytest tests/unit/test_history.py` ran successfully.
- Verified domain model behavior with strictly frozen schemas.

## Known blockers

- None

## Exact next actions

1. Begin T320: Implement pure feature helpers.
2. Develop pure feature functions/classes for Opening Range calculation, ATR/true range, and session VWAP required by the ORB strategy.

## Resume note

Safe to resume. Work continues with `T320`.
