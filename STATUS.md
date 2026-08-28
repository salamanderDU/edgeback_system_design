# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29 (Asia/Bangkok)
**Project state:** T320_COMPLETE
**Current milestone:** M3 — Strategy API, features, execution, and engine core
**Current task:** T330 — ORB strategy
**Current task status:** TODO
**Working tree:** T320 completed. Created pure feature helpers for Opening Range, ATR, and Volume Ratio. Unit tests verified correctly.

## Current objective

Begin T330: Implement ORB strategy from its hypothesis spec and strategy tests.

## Completed in the latest design session

- Created `calculate_opening_range`, `true_range`, `calculate_atr`, and `calculate_volume_ratio` in `src/edgeback/features/`.
- Wrote boundary tests in `tests/unit/test_features.py` which all passed.
- Marked T320 as DONE in TASK.md.

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
- Feature helpers `range.py`, `indicators.py`

## Files expected to be created next

- `strategies/opening_range_breakout.py`
- `tests/unit/test_strategy_orb.py`

## Validation performed

- `python -m pytest tests/unit/test_features.py` ran successfully.

## Known blockers

- None

## Exact next actions

1. Begin T330: Implement ORB strategy.
2. Develop `strategies/opening_range_breakout.py` implementing the rules in `strategy_specs/opening_range_breakout.yaml`.

## Resume note

Safe to resume. Work continues with `T330`.
