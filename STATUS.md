# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29 (Asia/Bangkok)
**Project state:** T300_COMPLETE
**Current milestone:** M3 — Strategy API, features, execution, and engine core
**Current task:** T310 — Implement causal history API and future-access guard tests
**Current task status:** TODO
**Working tree:** T300 completed with domain models, context, base class, and registry. Tests pass.

## Current objective

Begin T310: Implement causal history API and future-access guard tests to ensure strategies cannot peek at future data.

## Completed in the latest design session

- Created `OrderEvent` model in `src/edgeback/domain/orders.py`.
- Created `StrategyMetadata` in `src/edgeback/strategy/models.py`.
- Defined `StrategyContext` ABC in `src/edgeback/strategy/context.py`.
- Created `Strategy` base class in `src/edgeback/strategy/base.py`.
- Implemented `register_strategy`, `get_strategy_class` in `src/edgeback/strategy/registry.py`.
- Added unit tests in `tests/unit/test_strategy.py` which pass correctly.
- Marked T300 as DONE in TASK.md.

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

## Files expected to be created next

- `src/edgeback/strategy/history.py` (or similar for context implementation)
- `tests/unit/test_history.py`

## Validation performed

- `pytest tests/unit/test_strategy.py` ran successfully.

## Known blockers

- None

## Exact next actions

1. Begin T310: Implement causal history API and future-access guard tests.
2. Develop a concrete implementation of `StrategyContext` that wraps data and enforces time boundaries.

## Resume note

Safe to resume. Work continues with `T310`.
