# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** T450_COMPLETE
**Current milestone:** M4 — Event engine, execution, portfolio, and risk
**Current task:** T450 — Multi-symbol engine
**Current task status:** DONE (acceptance criteria met; evidence recorded in TASK.md)
**Working tree:** M4 single- and multi-symbol engines complete. All gates green: 178 tests pass, Ruff lint/format pass, mypy clean (49 source files).

## Current objective

Next: **T460 — Session liquidation** per docs/04 §10: normal and early-close forced liquidation using the calendar-provided close (`force_flat_at_session_end=true` default); forced exits tagged `FORCED_SESSION_CLOSE`; strategy cannot inspect the final-bar close and request a same-close fill; no hard-coded 16:00.

## Completed in this session

- **T450 DONE — multi-symbol engine.**
  - `src/edgeback/engine/allocation.py` (new): `IntentAllocator` protocol, `PriorityThenSymbolAllocator`, `AllocationContext`, `build_allocator` (fails fast on unknown names). Shared-capital batch semantics: candidates sorted by `(-priority, canonical symbol, creation order)`; each evaluated against projected cash/gross exposure reserving earlier-accepted notional (docs/02 §7).
  - `src/edgeback/engine/multi_symbol.py` (new): `MultiSymbolEventEngine`, `MultiSymbolRunResult`, `run_multi_symbol_backtest`. Bars merged by `bar_end_utc`; per-symbol strategy instances in canonical symbol order; one shared broker/ledger/risk manager; per-symbol warmup isolation; per-symbol reference prices/bar volumes/estimated costs for the risk batch; accepted orders `eligible_from=bar_end_utc`; failures retain diagnostics.
  - `src/edgeback/execution/fill_engine.py`: `on_bar`/`on_bars` now match only orders whose `order.symbol == bar.symbol` (ADR-013 cross-symbol correctness fix).
  - `src/edgeback/risk/manager.py`: `RiskContext.bar_volumes` + `estimated_cost_per_share_by_symbol`; `OrderIntent.priority` propagated to built orders.
  - `src/edgeback/domain/orders.py`: additive `OrderIntent.priority` (docs/05 §7).
  - `src/edgeback/engine/__init__.py`: exports multi-symbol API.
  - ADR-013 recorded (per-symbol instances, broker symbol filter, shared-capital allocator design).
  - `tests/unit/test_multi_symbol_engine.py` (new, 14 tests) + `tests/unit/test_fill_engine.py` (1 updated + 1 new symbol-filter test).

## Files changed

- `src/edgeback/engine/allocation.py` (new), `src/edgeback/engine/multi_symbol.py` (new), `src/edgeback/engine/__init__.py`
- `src/edgeback/execution/fill_engine.py`, `src/edgeback/risk/manager.py`, `src/edgeback/domain/orders.py`
- `tests/unit/test_multi_symbol_engine.py` (new), `tests/unit/test_fill_engine.py`
- `DECISIONS.md` (ADR-013), `TASK.md` (T450 DONE), `STATUS.md`

## Validation (exact commands)

- `pytest` → 178 passed (15 new; 163 baseline preserved)
- `ruff check .` → all passed
- `ruff format --check .` → 91 files formatted
- `mypy src` → no issues in 49 source files

## Blockers

- None.

## Notes for next session

- Session-close liquidation (docs/04 §10) is out of T440/T450 scope → T460.
- Warmup uses strategy `warmup_bars` bar-count gate; insufficient-warmup failure deferred (T460/T800).
- Engines consume `Sequence[Bar]` directly; repository/manifest wiring → T500/T640.
- Estimated round-trip cost per share = 2 × 1-share decomposition (documented in code).
- `pyproject.toml` has an unused `module = ['tests.*']` section noted by mypy (pre-existing; clean-up optional).

## Exact next actions

1. Mark T460 IN_PROGRESS in `TASK.md`; update this file.
2. Implement per-session forced liquidation in the engine(s): on the final regular-session bar of each session, liquidate open positions at final-bar close plus adverse slippage/costs, tagged `FORCED_SESSION_CLOSE` (docs/04 §10). Early-close days must use the calendar-provided close — no hard-coded 16:00.
3. Ensure strategy cannot use the final close to request a same-close fill (ADR-007); liquidation runs after strategy dispatch or is engine-generated only.
4. Add `tests/unit/test_session_liquidation.py` (normal close, early close via `tests/fixtures/synthetic.py` early-close fixture, tagging, no-same-close-exploit, multi-symbol flat-at-close).
5. Run pytest/ruff/mypy; record evidence; T460 DONE.

## Resume note

Safe to resume. T450 done with evidence. Next unblocked: T460 (dep T440 DONE; T450 also DONE).