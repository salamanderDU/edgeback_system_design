# TASK.md — Durable Implementation Backlog

Last design update: 2026-08-21  
Allowed states: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`  
Current milestone: M4 — Event engine, execution, portfolio, and risk  
Current task: T460

## Update rules

- Change a task to `IN_PROGRESS` before editing implementation files.
- A `DONE` task must include validation evidence in its detail section.
- When blocked, state the blocker and the smallest unblocking action.
- Update `STATUS.md` at task start, task completion, and before stopping.
- Do not delete completed task history. Add corrective tasks when regressions appear.

## Milestone summary

| Milestone | Name | Status |
|---|---|---|
| M0 | Bootstrap and quality baseline | DONE |
| M1 | Configuration and domain models | DONE |
| M2 | Calendar, data schema, repository, and fixtures | DONE |
| M3 | Strategy contract and ORB plugin | DONE |
| M4 | Event engine, execution, portfolio, and risk | DONE |
| M5 | Metrics, artifacts, registry, and reports | TODO |
| M6 | CLI and free-data adapters | TODO |
| M7 | Sweeps, walk-forward, and robustness | TODO |
| M8 | Hardening, documentation, and MVP acceptance | TODO |


## Task index

| ID | Milestone | Status | Depends on | Deliverable |
|---|---|---|---|---|
| T000 | M0 | DONE | — | Create Python project skeleton and preserve design docs |
| T010 | M0 | DONE | T000 | Configure pytest, Ruff, type checking, and offline CI baseline |
| T020 | M0 | DONE | T000 | Add logging, error hierarchy, `.env.example`, and ignore rules |
| T100 | M1 | DONE | T010 | Implement strict Pydantic configuration models |
| T110 | M1 | DONE | T100 | Implement YAML loader, precedence, and CLI-safe overrides |
| T120 | M1 | DONE | T100 | Implement canonical domain models/enums and serialization |
| T130 | M1 | DONE | T110,T120 | Implement config hashing and reproducibility metadata capture |
| T200 | M2 | DONE | T120 | Implement trading calendar interface and XNYS adapter |
| T210 | M2 | DONE | T120 | Implement canonical bar schema and validation report models |
| T220 | M2 | DONE | T210 | Implement local CSV/Parquet provider and normalization |
| T230 | M2 | DONE | T200,T210 | Implement Parquet repository, partitions, and dataset manifests |
| T240 | M2 | DONE | T230 | Build deterministic fixture datasets and validation/golden inputs |
| T300 | M3 | DONE | T120,T240 | Implement strategy base, context, intents, and trusted registry |
| T310 | M3 | DONE | T300 | Implement causal history API and future-access guard tests |
| T320 | M3 | DONE | T300,T310 | Implement pure feature helpers needed by ORB |
| T330 | M3 | DONE | T320 | Implement ORB strategy from its hypothesis spec and strategy tests |
| T340 | M3 | DONE | T300 | Implement strategy list/describe service APIs |
| T400 | M4 | DONE | T120,T240 | Implement portfolio ledger and accounting invariants |
| T410 | M4 | DONE | T120 | Implement commission, spread, and slippage models |
| T420 | M4 | DONE | T410 | Implement order lifecycle and fill rules for market/limit/stop/bracket |
| T430 | M4 | DONE | T400,T420 | Implement risk sizing, limits, reason codes, and daily lockout |
| T440 | M4 | DONE | T200,T310,T330,T400,T420,T430 | Implement deterministic single-symbol event engine |
| T450 | M4 | DONE | T440 | Add multi-symbol merge, shared capital, and allocation ordering |
| T460 | M4 | DONE | T440 | Add session close liquidation, early-close tests, and failure checkpoints |
| T500 | M5 | TODO | T440 | Implement intents/orders/fills/trades/equity artifact tables |
| T510 | M5 | TODO | T500 | Implement performance/trade/cost metrics with edge cases |
| T520 | M5 | TODO | T500 | Implement atomic run writer, schema validation, and checksums |
| T530 | M5 | TODO | T520 | Implement SQLite run registry and immutable completed runs |
| T540 | M5 | TODO | T510,T520 | Implement HTML report and warning/conclusion sections |
| T600 | M6 | TODO | T110,T230,T340,T440,T520 | Implement Typer CLI and `doctor` |
| T610 | M6 | TODO | T230 | Implement yfinance adapter with explicit capability/limitation metadata |
| T620 | M6 | TODO | T230 | Implement Alpaca IEX adapter with environment-only credentials |
| T630 | M6 | TODO | T600,T610,T620 | Implement data download/validate/list commands and network markers |
| T640 | M6 | TODO | T600,T540 | Implement backtest run/batch, run list/show, and report commands |
| T700 | M7 | TODO | T510,T530,T640 | Implement session-based train/validation/test splits |
| T710 | M7 | TODO | T700 | Implement deterministic parameter sweep and trial registry |
| T720 | M7 | TODO | T710 | Implement anchored/rolling walk-forward orchestration |
| T730 | M7 | TODO | T720 | Implement cost stress, parameter-neighborhood, concentration, bootstrap |
| T740 | M7 | TODO | T730 | Implement research gates and conclusion labels |
| T800 | M8 | TODO | T640,T740 | Run complete offline MVP acceptance scenario |
| T810 | M8 | TODO | T630,T800 | Run optional provider smoke tests and document observed limitations |
| T820 | M8 | TODO | T800 | Finalize user/strategy/provider authoring documentation |
| T830 | M8 | TODO | T800,T820 | Produce release checklist, version 0.1.0, and final safe handoff |

---

## Detailed tasks and acceptance evidence

### T000 — Create Python project skeleton

**Status:** DONE  
**Deliverables:** `pyproject.toml`, `src/edgeback/`, `tests/`, `strategies/`, package/CLI placeholders, design files retained at root.  
**Acceptance:** package imports; no design file is lost; no generated data committed.  
**Evidence:** Created directories, ran `pytest tests/test_import.py`, `ruff check .`, and `ruff format .`. Tests passed, no errors.

### T010 — Quality baseline

**Status:** DONE  
**Acceptance:** `pytest`, `ruff check .`, `ruff format --check .`, and chosen static type checker run on the skeleton; core tests require no network.  
**Evidence:** Configured `mypy` in `pyproject.toml`, added dev dependency for parsing, format and rules passed successfully.

### T020 — Operational baseline

**Status:** DONE  
**Acceptance:** structured logging utility, typed application errors, `.env.example`, and ignore rules cover `.env`, `data/`, `runs/`, caches, virtual environments, SQLite runtime files, and provider payloads. Secrets redaction test exists.  
**Evidence:** Created `utils.py`, `secrets.py`, `test_secrets.py`, expanded `.gitignore`, and tests pass.

### T100 — Configuration models

**Status:** DONE  
**Acceptance:** models cover all sections in `configs/example_backtest.yaml`; unknown keys fail; cross-field date/risk/order constraints tested; config objects are frozen after resolution.  
**Evidence:** Created `src/edgeback/config/models.py` with frozen BaseStrictModel and all configuration structures matching the example yaml. Implemented validators for dates and risk times. Tests explicitly verify `ValidationError` on extra fields, frozen reassignment, and cross-field logic. Tests ran successfully.

### T110 — Loader and overrides

**Status:** DONE  
**Acceptance:** documented precedence works; `--symbol` replacement and typed `--param` overrides tested; unsafe YAML tags rejected.  
**Evidence:** Created `src/edgeback/config/loader.py`, implemented safe loading, override parsing, and config resolution. Tests verify yaml safety, overrides execution, and config assembly correctly resolving configurations. Installed PyYAML and types.

### T120 — Domain models

**Status:** DONE  
**Acceptance:** typed Bar, Intent, Order, Fill, Position, events, reason codes, and statuses serialize deterministically; invalid states rejected.  
**Evidence:** Created `bars.py`, `orders.py`, `fills.py`, and `positions.py` in `src/edgeback/domain`. Created tests in `tests/unit/test_domain_models.py` verifying model initialization and invalid state rejection, including OHLC limits and tz validation. All tests and checks passed.

### T130 — Reproducibility metadata

**Status:** DONE  
**Acceptance:** stable canonical config hash; Git/dependency/seed metadata captured without exposing sensitive host data; dirty tree noted.  
**Evidence:** Implemented `RunMetadata` strict model in `src/edgeback/artifacts/reproducibility.py`. Methods explicitly gather Git metadata through subprocess without exposing paths. `config_hash` strips `report` structure intentionally for deterministic logic hashing. Wrote `tests/unit/test_reproducibility.py` to confirm the model instantiation, missing git fallback, and hashing rules. Fully mypy and test verified.

### T200 — Calendar

**Status:** DONE  
**Acceptance:** normal day, holiday, daylight-saving period, and early-close fixtures; no fixed UTC-offset logic.  
**Evidence:** Created `TradingCalendar` protocol in `src/edgeback/calendar/interfaces.py`. Implemented `XNYSCalendar` using `pandas_market_calendars`. Validated unit tests in `tests/unit/test_calendar.py` covering normal times, early closures (July 3rd), holidays (New Year's Day), and winter/summer boundary handling. Mypy typing passed cleanly with assertions.

### T210 — Bar schema and validation models

**Status:** DONE  
**Acceptance:** matches `schemas/bar.schema.json`; timezone-naive, duplicate, invalid OHLC, incomplete, mixed-feed cases tested.  
**Evidence:** Created `src/edgeback/data/schema.py` exporting `canonical_bar_schema` using PyArrow matching JSON constraints. Created `DataValidationReport` logic catching empty/missing properties, naive Pandas timezone constructs, invalid OHLC boundaries, negative volumes, and identical duplicate bar overlapping rows. Tests validated safely in `tests/unit/test_data_validation.py`. Cleaned Mypy restrictions explicitly covering Pandas warning types over timezone awareness.

### T220 — Local provider

**Status:** DONE  
**Acceptance:** imports mapped CSV and Parquet with explicit timestamp semantics/timezone; ambiguous input fails; provider contract tests pass.  
**Evidence:** Created `src/edgeback/data/providers/interfaces.py` and `src/edgeback/data/providers/local.py` for mapping generic naive temporal times through pandas to proper timezone specific boundaries via config parameters alongside mapping capabilities to validate data. Integrated with testing assertions across `test_local_provider.py`.

### T230 — Repository and manifests

**Status:** DONE  
**Acceptance:** atomic Parquet partitions, deterministic dataset hash, manifest/validation files, no silent provider mixing.  
**Evidence:** Developed `src/edgeback/data/manifest.py` containing explicit structures aligning with dataset JSON constraints. Implemented `src/edgeback/data/repository.py` driving pyarrow chunk configurations and checksum configurations deduplicating fields identically to standard. Test outputs verified securely under isolated Pytest execution.

### T240 — Fixtures

**Status:** DONE  
**Acceptance:** tiny single/multi-symbol sessions include normal fills, gaps, ambiguous brackets, missing bars, and early close; expected outputs are human-readable.  
**Evidence:** Completed `tests/fixtures/synthetic.py` mapping multiple fixtures testing `validate_dataframe()` bounds with explicit requirements on regular schedules, simulated timezone shifts tracking 9:30 AM starts up to early closures alongside ambiguous bounding conditions. Validations passed cleanly under `test_fixtures.py`. Mypy constraints solved via variable mappings bounds.

### T300 — Strategy contract and registry

**Status:** DONE  
**Acceptance:** trusted registry, strict parameter models, lifecycle hooks, read-only context, serializable state, and contract tests.  
**Evidence:** Created `src/edgeback/strategy` module including models, context, base class, and registry. Implemented strict parameter handling, read-only StrategyContext ABC, and registration patterns avoiding unauthorized code evaluation. Tests pass successfully in `tests/unit/test_strategy.py`.

### T310 — Causal history

**Status:** DONE  
**Acceptance:** context cannot return data after engine time; future mutation sentinel passes.  
**Evidence:** Created `src/edgeback/strategy/history.py` providing `CausalStrategyContext` that returns only bars ending on or before `engine_time_utc`. Attempted bar mutations raise Pydantic `ValidationError`. List mutations do not affect underlying context state. Tested via `tests/unit/test_history.py` which passes `pytest`.

### T320 — Feature helpers

**Status:** DONE  
**Acceptance:** causal opening range, ATR/true range, session VWAP or volume ratio helpers needed by ORB; boundary tests.  
**Evidence:** Created `src/edgeback/features/range.py` for Opening Range and `src/edgeback/features/indicators.py` for ATR and Volume Ratio. Added tests in `tests/unit/test_features.py` which pass correctly.

### T330 — ORB strategy

**Status:** DONE  
**Acceptance:** implements `strategy_specs/opening_range_breakout.yaml`; no ticker literals; session reset, cutoff, one-trade controls, stop/target intents, and golden test pass.  
**Evidence:** Implemented strategy tests in `tests/unit/test_strategy_orb.py` covering session boundary, valid intents and bracket, cutoff limits, max trades, and volume ratio rules. All tests passed under `pytest`.

### T340 — Strategy services

**Status:** DONE  
**Acceptance:** list/describe returns deterministic metadata and parameter schema; duplicate ID/version conflict fails.  
**Evidence:** Implemented `src/edgeback/strategy/services.py` with `discover_strategies`, `list_strategies_service`, `describe_strategy_service`, and models `StrategySummary` and `StrategyDetail`. Tested deterministic list sorting, parameter schema extraction, metadata discovery, and duplicate ID conflict handling in `tests/unit/test_strategy_services.py`. All tests passed under pytest, Ruff, and mypy.


### T400 — Portfolio ledger

**Status:** DONE  
**Acceptance:** long/short accounting, fees, mark-to-market, realized/unrealized P&L, exposure, and reconciliation invariants pass.  
**Evidence:** Implemented `src/edgeback/portfolio/accounting.py` (pure helpers: Decimal ROUND_HALF_UP money rounding, signed-quantity/cash-delta/effective-price decomposition, weighted-average price, and an independent `project_fills` replay) and `src/edgeback/portfolio/ledger.py` (`PortfolioLedger` mutable state machine with cash/leverage guards evaluated against projected state before mutation, timezone-aware non-decreasing timestamp and monotonic order-id guards, mark-to-market, realized/unrealized P&L, gross/net exposure, equity, session P&L accumulator, and `reconcile()` returning a `ReconciliationReport`). Accounting model: positions are signed net shares; realized P&L uses base execution prices while spread/slippage/commission flow through cash, so a flat round trip satisfies `cash_change = realized_pnl - total_costs`. Updated `src/edgeback/portfolio/__init__.py` to export the public API. Added `tests/unit/test_portfolio.py` (26 tests) covering long/short round trips with costs, weighted-average adds, partial/full/crossing closes, mark-to-market and exposure, cash/leverage guards leaving state untouched, timezone/order-ID/non-positive-share guards, deterministic position snapshots, and hand-computed reconciliation invariants. Validation: `pytest` 90 passed (26 new portfolio tests), `ruff check .` all passed, `ruff format --check .` 80 files formatted, `mypy src` no issues in 43 source files.

### T410 — Cost models

**Status:** DONE  
**Acceptance:** zero/fixed/per-share/bps commission; spread and bps slippage; decomposition exact within rounding policy.  
**Evidence:** Extended `src/edgeback/config/models.py` with typed `Literal` models and per-model commission parameters (`usd_per_order`, `usd_per_share`, `minimum_usd_per_order`, `bps_of_notional`) plus cross-field validation. Implemented `src/edgeback/execution/costs.py` (zero/fixed-per-order/per-share-with-minimum/bps commission; fixed-bps half-side spread; fixed-bps slippage; `CostDecomposition`; `ExecutionCosts.decompose`; factory functions) and exported it from `src/edgeback/execution/__init__.py`. Added `tests/unit/test_cost_models.py` (17 tests) covering each model, the example-backtest decomposition, config rejections, direction-sensitive effective price, and a flat round-trip cash-consistency invariant. Validation: `pytest` 107 passed (17 new), `ruff check .` passed, `ruff format --check .` 82 files formatted, `mypy src` no issues in 44 sources.

### T420 — Fill engine

**Status:** DONE  
**Acceptance:** next-open market, limit improvement, gap-through stop, bracket activation, same-bar policies, expiry, and deterministic ordering tested.  
**Evidence:** Extended `src/edgeback/domain/orders.py` with timeline/ordering fields (`eligible_from_utc`, `expires_at_utc`, `parent_order_id`, `priority`, `creation_sequence` — additive) and extended `src/edgeback/config/models.py` `EngineConfig.same_bar_bracket_policy` to the four documented policies. Implemented `src/edgeback/execution/fill_engine.py` (`SimulatedBroker`): deterministic working-order book; next-bar market fill at open; buy/sell limit improvement; gap-through stop vs stop-touch; bracket children activation at entry-bar open with same-bar ambiguity resolution (stop_first/target_first/nearest_to_open/reject_ambiguous_bar); unfilled-order expiry without backfill; sibling cancellation when one protective child fills; clock/eligibility/status guards; cost-decomposed `Fill` output (T410 bundle → T400 ledger); exported from `src/edgeback/execution/__init__.py`. Added `tests/unit/test_fill_engine.py` (20 tests) covering the docs/08 §3 mandatory timing tests (no same-bar fill, gap-through stop, stop-touch, limit improvement, both-stop-and-target touched under all four policies, bracket activation into later bars, missing-next-bar expiry, deterministic ordering, lifecycle guards, and fill cost decomposition). Validation: `pytest` 127 passed (20 new fill-engine tests), `ruff check .` passed, `ruff format --check .` 84 files formatted, `mypy src` no issues in 45 source files.

### T430 — Risk manager

**Status:** DONE  
**Acceptance:** risk-per-trade formula, fixed sizing modes, exposure/cash/participation caps, daily loss/trade lockouts, reason codes, and protective-exit exception tests.  
**Evidence:** Extended `src/edgeback/config/models.py` `RiskSizingConfig` with typed sizing models (`risk_per_trade`, `fixed_shares`, `fixed_notional`, `percent_equity`) and cross-field validation. Implemented `src/edgeback/risk/manager.py` (`RiskManager`, `RiskContext`, `RiskDecision`, `RiskReason`, `risk_manager_from_config`) implementing the docs/04 §8 risk pipeline: entry-time window, direction permission, daily-loss/max-trades/consecutive-loss lockouts, cooldown, duplicate-order detection, max-concurrent positions, risk-per-trade/fixed-share/fixed-notional/percent-equity sizing, per-position cap, gross-exposure cap, cash limit, volume-participation cap (reject or resize), and protective-exit bypass (docs/04 §9). Added `OrderIntent.protective_exit` (additive, defaulted False) and exported the risk package. Added `tests/unit/test_risk_manager.py` (27 tests) covering the docs/04 §8 risk-per-trade formula (with and without estimated cost), all sizing modes, caps with reason codes, daily lockouts, cooldown, duplicate/concurrent checks, protective-exit exemption, session reset, and missing-reference-price rejection. Validation: `pytest` 154 passed (27 new risk tests), `ruff check .` passed, `ruff format --check .` 86 files formatted, `mypy src` no issues in 46 source files.

### T440 — Single-symbol engine

**Status:** DONE  
**Acceptance:** exact event sequence from design; no same-bar signal fill; deterministic rerun; failure retains diagnostics.  
**Evidence:** Implemented `src/edgeback/engine/event_loop.py` (SingleSymbolEventEngine, EngineRunResult, EquityPoint, EngineError, run_single_symbol_backtest) implementing docs/04 §2-3,13: per-session bar loop; broker evaluates eligible working orders; ledger applies fills with monotonic order ids; closed trades feed risk counters; mark-to-market each bar; strategy dispatch via CausalStrategyContext; risk batch evaluation (T430); accepted orders submitted with eligible_from_utc = bar_end_utc (next-bar start per ADR-007); warmup suppresses orders with WARMUP warnings (docs/04 §11); failures return status=FAILED with retained traceback and partial state (docs/02 §9). Exported engine API from src/edgeback/engine/__init__.py. Completed the documented strategy contract per ADR-012: OrderIntent.take_profit_price, risk manager builds bracket orders from stop+target, ORB emits take_profit_price = entry +/- reward_risk * stop_distance. Added tests/unit/test_event_engine.py (9 tests): no-same-bar fill at next open, exact events + eligible_from=signal bar end + acceptance/fill event order, full bracket lifecycle entry-to-target-exit with sibling cancellation and ledger reconciliation, warmup isolation, deterministic rerun identical outputs, failure retains diagnostics and partial state, bad-data-contract and multi-symbol FAILED results, causal-context never exposes future bars. Validation: pytest 163 passed (9 new engine tests), ruff check . clean, ruff format --check . 88 files formatted, mypy src no issues in 47 source files.

### T450 — Multi-symbol engine

**Status:** DONE  
**Acceptance:** timestamp merge, symbol ordering, shared capital, simultaneous intent allocation, and symbol-order-independent economic result under declared allocator.  
**Evidence:** Implemented `src/edgeback/engine/allocation.py` (`allocator` new; ADR-013): `IntentAllocator` protocol, `PriorityThenSymbolAllocator` (sorts candidates by (-priority, canonical symbol, creation order) and evaluates each against a projected cash/gross-exposure state that reserves earlier-accepted notional — shared-capital batch semantics, docs/02 §7), `build_allocator` failing fast on unknown names. Implemented `src/edgeback/engine/multi_symbol.py` (`MultiSymbolEventEngine`, `MultiSymbolRunResult`, `run_multi_symbol_backtest`): bars merged by `bar_end_utc`; per-symbol strategy instances in canonical symbol order (ADR-013); one shared broker/ledger/risk manager; broker evaluates only orders whose `order.symbol == bar.symbol` (ADR-013 symbol filter); per-symbol warmup isolation; per-symbol reference prices/bar volumes/estimated costs for the risk batch; accepted orders eligible_from=bar_end_utc (ADR-007); failures retain diagnostics (docs/02 §9). Extended `src/edgeback/risk/manager.py` `RiskContext` with `bar_volumes` + `estimated_cost_per_share_by_symbol` and propagated `OrderIntent.priority` to built orders. Added additive `OrderIntent.priority` (docs/05 §7). Updated `src/edgeback/engine/__init__.py`. Added `tests/unit/test_multi_symbol_engine.py` (14 tests: timestamp merge + per-symbol fills/no-same-bar, canonical symbol dispatch order, per-symbol instance isolation, shared-capital allocation with GROSS_EXPOSURE_LIMIT rejection, priority-then-symbol ordering, symbol-order-independent economics across reversed bars/config, per-symbol warmup suppression, deterministic rerun, duplicate/overlap/incomplete-bar rejection, failure diagnostics retention, allocator fail-fast) and `tests/unit/test_fill_engine.py` (updated deterministic-ordering test to per-symbol bars + new `test_broker_symbol_filter_prevents_cross_symbol_fill`). Validation: `pytest` 178 passed (15 new), `ruff check .` passed, `ruff format --check .` 91 files formatted, `mypy src` no issues in 49 source files.

### T460 — Session liquidation

**Status:** DONE  
**Acceptance:** normal and early close; forced exits tagged; strategy cannot exploit same-close information.  
**Evidence:** Implemented `docs/04 §10` forced session-close liquidation (ADR-014). `src/edgeback/execution/fill_engine.py`: `SimulatedBroker.force_flat_at_close(positions, bar)` builds deterministic closing orders per open position, fills at the final-bar close plus T410 cost decomposition, tags order/fill ``FORCED_SESSION_CLOSE``, and cancels still-open bracket children with ``FORCED_SESSION_CLOSE_PARENT``. `src/edgeback/engine/event_loop.py`: single-symbol engine calls forced close after each session's bar loop (post strategy dispatch, pre `on_session_end`) when `force_flat_at_session_end=true`. `src/edgeback/engine/multi_symbol.py`: timestamp loop now detects session boundaries via `is_session_start`/`is_session_end` and liquidates each symbol at its own final bar close. Both engines use the final bar's close as the calendar-provided close (no hard-coded 16:00; early closes honored implicitly). Strategy signals are never filled on their signal bar close — only the engine-generated forced close fills then (ADR-007). Added `tests/unit/test_session_liquidation.py` (7 tests): normal-close forced liquidation at final close with tag, early-close (13:00 ET) liquidation, no same-close exploit, protective children cancelled after forced close, `force_flat_at_session_end=false` disables the behavior, multi-symbol each-symbol-own-close, and deterministic rerun. T440/T450 test configs now use `force_flat_at_session_end=false` to keep their pre-T460 fill-count scopes. Validation: `pytest` 185 passed (178 baseline preserved + 7 new), `ruff check .` clean, `ruff format --check .` 92 files formatted, `mypy src` no issues in 49 source files.

### T500 — Canonical result tables

**Status:** TODO  
**Acceptance:** complete linkage among intents/orders/fills/trades; Parquet schemas stable; reason and cost fields present.  
**Evidence:** _not yet run_

### T510 — Metrics

**Status:** TODO  
**Acceptance:** manual fixtures and zero/undefined cases; units and observation counts; `null` plus reason for undefined.  
**Evidence:** _not yet run_

### T520 — Run writer

**Status:** TODO  
**Acceptance:** temp-to-final atomic transition, required artifacts/schema/checksum validation, `FAILED` diagnostics, no overwrite.  
**Evidence:** _not yet run_

### T530 — Registry

**Status:** TODO  
**Acceptance:** SQLite records logical identity, state, paths, parent/fold links; registry loss does not make run folders unreadable.  
**Evidence:** _not yet run_

### T540 — HTML report

**Status:** TODO  
**Acceptance:** all required sections, limitations/warnings, cost-inclusive figures, conclusion label; report generation does not alter metrics.  
**Evidence:** _not yet run_

### T600 — CLI and doctor

**Status:** TODO  
**Acceptance:** command surface and exit codes match design; `doctor` redacts secrets and works offline.  
**Evidence:** _not yet run_

### T610 — yfinance adapter

**Status:** TODO  
**Acceptance:** explicit interval/session/adjustment arguments, recent-lookback validation, cache/manifest metadata, bounded retries, mocked tests plus optional smoke test.  
**Evidence:** _not yet run_

### T620 — Alpaca IEX adapter

**Status:** TODO  
**Acceptance:** environment-only keys, explicit `feed=iex`, capability warning, pagination/rate handling, mocked tests plus optional smoke test.  
**Evidence:** _not yet run_

### T630 — Data CLI

**Status:** TODO  
**Acceptance:** provider list, download, import, validate, and dataset list; no provider fallback; meaningful exit codes.  
**Evidence:** _not yet run_

### T640 — Backtest/run CLI

**Status:** TODO  
**Acceptance:** run/batch and run/report inspection; symbol/parameter overrides; final artifact path; offline missing-data failure.  
**Evidence:** _not yet run_

### T700 — Research splits

**Status:** TODO  
**Acceptance:** chronological session splits, warmup isolation, embargo, immutable final test.  
**Evidence:** _not yet run_

### T710 — Sweep

**Status:** TODO  
**Acceptance:** bounded deterministic grid/random trials, all trials persisted, no final-test selection.  
**Evidence:** _not yet run_

### T720 — Walk-forward

**Status:** TODO  
**Acceptance:** rolling/anchored folds, fit/select in train only, concatenated OOS trades, fold metadata.  
**Evidence:** _not yet run_

### T730 — Robustness

**Status:** TODO  
**Acceptance:** cost multipliers, delayed entry, parameter neighborhood, concentration, session bootstrap with seed.  
**Evidence:** _not yet run_

### T740 — Gates/conclusions

**Status:** TODO  
**Acceptance:** gate configuration, reasons, and allowed conclusion labels; no language implying guaranteed edge.  
**Evidence:** _not yet run_

### T800 — Offline MVP acceptance

**Status:** TODO  
**Acceptance:** all ten scenarios in `docs/08_TESTING_AND_ACCEPTANCE.md` pass from clean environment; evidence and artifact hashes recorded.  
**Evidence:** _not yet run_

### T810 — Provider smoke tests

**Status:** TODO  
**Acceptance:** tiny yfinance/Alpaca tests when access is available; observed capabilities and limitations documented; task may be `BLOCKED` without credentials but cannot block offline MVP.  
**Evidence:** _not yet run_

### T820 — Documentation

**Status:** TODO  
**Acceptance:** install/use, data import, strategy authoring, provider authoring, artifact interpretation, research workflow, and troubleshooting are accurate against version 0.1.0.  
**Evidence:** _not yet run_

### T830 — Release/handoff

**Status:** TODO  
**Acceptance:** version 0.1.0, release checklist, clean status, all quality gates, safe `STATUS.md` handoff, known limitations listed.  
**Evidence:** _not yet run_
