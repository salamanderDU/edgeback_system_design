# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** T430_COMPLETE
**Current milestone:** M4 — Event engine, execution, portfolio, and risk
**Current task:** T440 — Single-symbol engine
**Current task status:** TODO (dependencies T200, T310, T330, T400, T420, T430 all DONE)
**Working tree:** T400–T430 complete. All gates green: 154 tests pass, Ruff lint/format pass, mypy clean (46 source files).

## Current objective

T440: deterministic single-symbol event engine in `src/edgeback/engine/` per docs/04 §2-3,13 (exact event sequence, no same-bar signal fill, warmup isolation, deterministic rerun, failure diagnostics).

## Completed in the latest session

- T430 DONE — risk manager (`src/edgeback/risk/manager.py`): docs/04 §8 pipeline (entry window, direction, daily-loss/max-trades/consecutive-loss lockouts, cooldown, duplicates, max-concurrent, risk_per_trade/fixed_shares/fixed_notional/percent_equity sizing, per-position/gross/cash/participation caps, reason codes, protective-exit bypass). Extended `RiskSizingConfig` (typed models + validation), added `OrderIntent.protective_exit`, exported risk package. Tests: `tests/unit/test_risk_manager.py` (27). Validation: 154 passed, ruff clean, mypy clean (46 sources).
- T420 DONE (fill engine, 20 tests), T410 DONE (cost models, 17 tests), T400 DONE (portfolio ledger, 26 tests).

## Implementation completed

- T430: `src/edgeback/risk/manager.py`, `__init__.py`; `RiskSizingConfig` typed models; `OrderIntent.protective_exit`; tests `test_risk_manager.py`.
- T420: `src/edgeback/execution/fill_engine.py`; `Order` timeline/ordering fields; 4-policy `same_bar_bracket_policy`; tests `test_fill_engine.py`.
- T410: `src/edgeback/execution/costs.py`; typed commission/spread/slippage configs; tests `test_cost_models.py`.
- T400: `src/edgeback/portfolio/accounting.py`, `ledger.py`; tests `test_portfolio.py`.
- (M0–M3 modules from earlier sessions.)

## Files changed in the latest session

- `src/edgeback/risk/manager.py`, `src/edgeback/risk/__init__.py` (new, T430)
- `src/edgeback/config/models.py` (T430 RiskSizingConfig + earlier T410/T420 edits)
- `src/edgeback/domain/orders.py` (T430 protective_exit + earlier T420 edits)
- `tests/unit/test_risk_manager.py` (new, 27 tests)
- `TASK.md` (T430 → DONE)
- `STATUS.md` (this checkpoint)

## Validation performed

- `python -m pytest` (154 passed — 27 new risk tests)
- `python -m ruff check .` (All checks passed)
- `python -m ruff format --check .` (86 files already formatted)
- `python -m mypy src` (Success: no issues found in 46 source files)

## Known blockers

- None

## Exact next actions

1. Mark T440 IN_PROGRESS in `TASK.md` and update this file.
2. Implement `src/edgeback/engine/event_loop.py` per docs/04 §13: per-session bar loop; broker evaluates eligible orders; ledger applies fills + marks to market; strategy dispatch (`on_session_start`/`on_bar`/`on_session_end`) via `CausalStrategyContext` (T310); risk batch evaluation (T430); accepted orders submitted with `eligible_from = next_bar_start` (T420); warmup disables orders.
3. Add `tests/unit/test_event_engine.py` (no same-bar fill, future mutation, warmup isolation, deterministic rerun, failure diagnostics).
4. Run `pytest`, `ruff check .`, `ruff format --check .`, `mypy src`; record evidence; mark T440 DONE.

## Resume note

Safe to resume. M4 supporting layers complete. Next task is T440 (single-symbol event engine), fully unblocked.