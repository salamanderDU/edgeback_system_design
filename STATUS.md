# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29 (Asia/Bangkok)
**Project state:** T330_COMPLETE
**Current milestone:** M3 — Strategy API, features, execution, and engine core
**Current task:** T340 — Strategy services
**Current task status:** TODO
**Working tree:** T330 complete. `strategies/opening_range_breakout.py` has been completely rewritten to align with the `Strategy` API, and tests are implemented in `tests/unit/test_strategy_orb.py`.

## Current objective

T340: Implement strategy list/describe service APIs.

## Completed in the latest design session

- Fixed incorrect base models in `strategies/opening_range_breakout.py`.
- Replaced mocked `OrderIntent` schema fields with properties matching `edgeback.domain.orders.OrderIntent`.
- Implemented `tests/unit/test_strategy_orb.py` simulating real market execution with `CausalStrategyContext`.
- Fixed data overlap and index issues with the mocked `Bar` objects for `pytest`.
- Ran `pytest` ensuring `test_strategy_orb.py` passes all logic bounds.
- Marked T330 as DONE in `TASK.md`.

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
- Opening Range Breakout Strategy `strategies/opening_range_breakout.py`
- ORB Strategy Tests `tests/unit/test_strategy_orb.py`

## Files expected to be created next

- `src/edgeback/strategy/services.py`
- `tests/unit/test_strategy_services.py`

## Validation performed

- `python -m pytest tests/unit/test_strategy_orb.py -s` ran successfully and passed 4/4 tests.

## Known blockers

- None

## Exact next actions

1. Start T340: Implement strategy list/describe service APIs.
2. Change T340 to IN_PROGRESS in TASK.md before editing code.

## Resume note

Safe to resume. The ORB strategy has been implemented and tested successfully, so now we are ready to move onto `T340`.