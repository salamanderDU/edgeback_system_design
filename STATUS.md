# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-29
**Project state:** M4_COMPLETE
**Current milestone:** M4 — Event engine, execution, portfolio, and risk (DONE)
**Current task:** T460 — Session liquidation
**Current task status:** DONE (acceptance criteria met; evidence recorded in TASK.md)
**Working tree:** M4 complete. All gates green: 185 tests pass, Ruff lint/format pass, mypy clean (49 source files).

## Current objective

Next: **T500 — Canonical result tables** (M5 — Metrics, artifacts, registry, and reports). T500 depends on T440 (DONE) and must implement the intents/orders/fills/trades/equity Parquet artifact tables with complete linkage, stable schemas, and reason/cost fields per `docs/07_CLI_CONFIG_AND_ARTIFACTS.md` §8-9. T500 is unblocked — the M4 engines produce all the tuples needed (intents, decisions, orders, fills, broker events, warnings, equity curve, reconciliation).

## Completed in this session

- **T460 DONE — session-close liquidation (M4 complete).**
  - `src/edgeback/execution/fill_engine.py`: new `SimulatedBroker.force_flat_at_close(positions, bar)` — deterministic per-position closing market orders, fill at the final-bar close (the documented ADR-007 same-close exception), T410 cost decomposition, tags `FORCED_SESSION_CLOSE`, cancels still-open bracket children with `FORCED_SESSION_CLOSE_PARENT`. `_make_fill` gained an optional explicit `action` parameter for engine-generated closing orders.
  - `src/edgeback/engine/event_loop.py`: single-symbol engine invokes forced close after each session's bar loop (post strategy dispatch, pre `on_session_end`) when `engine.force_flat_at_session_end=true`; applies fills with monotonic IDs, records closed trades, marks to market, appends an equity point.
  - `src/edgeback/engine/multi_symbol.py`: timestamp loop now detects session boundaries (`is_session_start`/`is_session_end`), accumulates per-session bars, and liquidates each symbol using that symbol's own final bar close; `on_session_end` moved to the end of each session (after forced close).
  - Close is derived from the final bar of the session data (the calendar-provided close by construction) — no hard-coded 16:00; early close tests confirm 13:00 ET.
  - ADR-014 recorded in `DECISIONS.md`.
  - `tests/unit/test_session_liquidation.py` (new, 7 tests): normal-close forced liquidation, early-close 13:00 ET, no same-close exploit (final-bar strategy intents never fill at that close), protective children cancelled after forced close, `force_flat_at_session_end=false` disables behavior, multi-symbol per-symbol-own-close, deterministic rerun.
  - `tests/unit/test_event_engine.py` and `tests/unit/test_multi_symbol_engine.py`: config helpers now set `force_flat_at_session_end=False` so their pre-T460 fill-count assertions stay scoped to their own invariants (ADR-014 documents this).

## Files changed

- `src/edgeback/execution/fill_engine.py` (force_flat_at_close + child cancellation + explicit fill action)
- `src/edgeback/engine/event_loop.py` (single-symbol forced close)
- `src/edgeback/engine/multi_symbol.py` (session boundary detection + per-symbol forced close)
- `tests/unit/test_session_liquidation.py` (new, 7 tests)
- `tests/unit/test_event_engine.py`, `tests/unit/test_multi_symbol_engine.py` (force_flat=False in test configs)
- `DECISIONS.md` (ADR-014), `TASK.md` (T460 DONE, M4 DONE), `STATUS.md`

## Validation (exact commands)

- `.venv/bin/python -m pytest` → 185 passed (178 baseline + 7 new; no regressions)
- `.venv/bin/ruff check .` → all passed
- `.venv/bin/ruff format .` → 4 files reformatted (88 unchanged); `.venv/bin/ruff format --check .` → 92 files already formatted
- `.venv/bin/python -m mypy src` → Success: no issues found in 49 source files

## Blockers

- None.

## Notes for next session

- M5 begins with T500 (canonical result tables). The engines already return `intents`, `decisions`, `orders`, `fills`, `broker_events`, `warnings`, `equity_curve`, and `reconciliation`; T500 must turn them into Parquet artifact tables with stable schemas, complete linkage, and reason/cost fields (`docs/07` §8-9).
- The `.env.example` referenced in `PROJECT_MANIFEST.yaml` exists at repo root (confirmed in tree listing during T460 session).
- `pyproject.toml` still has the unused `module = ['tests.*']` mypy section (pre-existing; clean-up optional).
- mypy's `.venv/bin/mypy` executable has a stale shebang (`edgeback_system_design_v1/.venv/bin/python3.13`); use `.venv/bin/python -m mypy src` instead.
- Session-close liquidation is engine-generated and tag-visible; reports/artifacts (T500+) should surface forced exits as required by docs/04 §14.
- Warmup uses strategy `warmup_bars` bar-count gate; insufficient-warmup failure deferred (T460 note carried over — still open, no task assigned yet).
- Engines consume `Sequence[Bar]` directly; repository/manifest wiring → T500/T640.

## Exact next actions

1. Mark T500 IN_PROGRESS in `TASK.md`; update this file.
2. Implement `src/edgeback/artifacts/` canonical result tables: intents (incl. rejected), orders with status transitions, fills with cost decomposition, trades with entry/exit linkage, and equity snapshots, as Parquet with stable schemas (`docs/07` §8, `docs/04` §14).
3. Persist resolved config, run metadata, data manifest, warnings, and logs per run.
4. Add tests for table linkage/schema/checksums; run pytest/ruff/mypy; record evidence; T500 DONE.

## Resume note

Safe to resume. M4 complete with evidence. Next unblocked: T500 (dep T440 DONE; no M4 blockers remain).