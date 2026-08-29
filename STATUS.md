# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** T440_COMPLETE
**Current milestone:** M4 — Event engine, execution, portfolio, and risk
**Current task:** T440 — Single-symbol engine
**Current task status:** DONE (acceptance criteria met; evidence recorded in TASK.md)
**Working tree:** M4 core complete. All gates green: 163 tests pass, Ruff lint/format pass, mypy clean (47 source files).

## Current objective

Next: **T450 — Multi-symbol engine** per docs/02 §7 + docs/04 §2-3: merge bars by `bar_end_utc`, symbol ordering for broker/`on_bar`, shared-capital ledger, simultaneous-intent risk batch, symbol-order-independent economics under `entry_allocation` (`priority_then_symbol`).

## Completed in this session

- **T440 DONE — single-symbol event engine.**
  - `src/edgeback/engine/event_loop.py` (new): `SingleSymbolEventEngine`, `EngineRunResult`, `EquityPoint`, `EngineError`, `run_single_symbol_backtest`. docs/04 §2-3,13 sequence: broker evaluates eligible orders (T420); ledger applies fills w/ monotonic ids (T400); closed trades feed risk counters; mark-to-market; strategy dispatch via `CausalStrategyContext` (T310); risk batch (T430); accepted orders `eligible_from_utc = bar_end_utc` (ADR-007); warmup suppresses orders + `WARMUP` warnings (docs/04 §11); failures → `status=FAILED` with traceback + partial state (docs/02 §9). Rejects empty/incomplete/overlapping/duplicate/mixed-symbol bars.
  - `src/edgeback/engine/__init__.py`: engine exports.
  - ADR-012 (`DECISIONS.md`): `OrderIntent.take_profit_price` completes docs/05 §7; risk builds bracket orders from stop+target; ORB emits target per `reward_risk`.
  - `domain/orders.py` + `risk/manager.py` + `strategies/opening_range_breakout.py`: ADR-012 changes.
  - `tests/unit/test_event_engine.py` (new, 9 tests).

## Files changed

- `src/edgeback/engine/event_loop.py` (new), `src/edgeback/engine/__init__.py`
- `src/edgeback/domain/orders.py`, `src/edgeback/risk/manager.py`, `strategies/opening_range_breakout.py`
- `tests/unit/test_event_engine.py` (new), `DECISIONS.md` (ADR-012), `TASK.md` (T440 DONE), `STATUS.md`

## Validation (exact commands)

- `pytest tests/unit/test_event_engine.py` → 9 passed
- `pytest` → 163 passed (9 new; no regressions)
- `ruff check .` → all passed
- `ruff format --check .` → 88 files formatted
- `mypy src` → no issues in 47 source files

## Blockers

- None.

## Notes for next session

- Session-close liquidation (docs/04 §10) is out of T440 scope → T460.
- Warmup uses strategy `warmup_bars` bar-count gate; insufficient-warmup failure deferred (T460/T800).
- Engine consumes `Sequence[Bar]`; repository/manifest wiring → T500/T640.
- Estimated round-trip cost per share = 2 × 1-share decomposition (documented in code).

## Exact next actions

1. Mark T450 IN_PROGRESS in `TASK.md`; update this file.
2. Implement multi-symbol per docs/02 §7 (merge by `bar_end_utc`; deterministic order; `on_bar` per symbol; batch risk; shared ledger; allocator).
3. Add `tests/unit/test_multi_symbol_engine.py`.
4. Run pytest/ruff/mypy; record evidence; T450 DONE.
5. Then T460 (session-close liquidation + early-close tests).

## Resume note

Safe to resume. T440 done with evidence. Next unblocked: T450 (dep T440 DONE).