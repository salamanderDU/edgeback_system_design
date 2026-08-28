# TASK.md — Durable Implementation Backlog

Last design update: 2026-08-21  
Allowed states: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`  
Current milestone: M0 — Repository bootstrap  
Current task: T000

## Update rules

- Change a task to `IN_PROGRESS` before editing implementation files.
- A `DONE` task must include validation evidence in its detail section.
- When blocked, state the blocker and the smallest unblocking action.
- Update `STATUS.md` at task start, task completion, and before stopping.
- Do not delete completed task history. Add corrective tasks when regressions appear.

## Milestone summary

| Milestone | Name | Status |
|---|---|---|
| M0 | Bootstrap and quality baseline | TODO |
| M1 | Configuration and domain models | DONE |
| M2 | Calendar, data schema, repository, and fixtures | TODO |
| M3 | Strategy contract and ORB plugin | TODO |
| M4 | Event engine, execution, portfolio, and risk | TODO |
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
| T310 | M3 | TODO | T300 | Implement causal history API and future-access guard tests |
| T320 | M3 | TODO | T300,T310 | Implement pure feature helpers needed by ORB |
| T330 | M3 | TODO | T320 | Implement ORB strategy from its hypothesis spec and strategy tests |
| T340 | M3 | TODO | T300 | Implement strategy list/describe service APIs |
| T400 | M4 | TODO | T120,T240 | Implement portfolio ledger and accounting invariants |
| T410 | M4 | TODO | T120 | Implement commission, spread, and slippage models |
| T420 | M4 | TODO | T410 | Implement order lifecycle and fill rules for market/limit/stop/bracket |
| T430 | M4 | TODO | T400,T420 | Implement risk sizing, limits, reason codes, and daily lockout |
| T440 | M4 | TODO | T200,T310,T330,T400,T420,T430 | Implement deterministic single-symbol event engine |
| T450 | M4 | TODO | T440 | Add multi-symbol merge, shared capital, and allocation ordering |
| T460 | M4 | TODO | T440 | Add session close liquidation, early-close tests, and failure checkpoints |
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

**Status:** TODO  
**Acceptance:** context cannot return data after engine time; future mutation sentinel passes.  
**Evidence:** _not yet run_

### T320 — Feature helpers

**Status:** TODO  
**Acceptance:** causal opening range, ATR/true range, session VWAP or volume ratio helpers needed by ORB; boundary tests.  
**Evidence:** _not yet run_

### T330 — ORB strategy

**Status:** TODO  
**Acceptance:** implements `strategy_specs/opening_range_breakout.yaml`; no ticker literals; session reset, cutoff, one-trade controls, stop/target intents, and golden test pass.  
**Evidence:** _not yet run_

### T340 — Strategy services

**Status:** TODO  
**Acceptance:** list/describe returns deterministic metadata and parameter schema; duplicate ID/version conflict fails.  
**Evidence:** _not yet run_

### T400 — Portfolio ledger

**Status:** TODO  
**Acceptance:** long/short accounting, fees, mark-to-market, realized/unrealized P&L, exposure, and reconciliation invariants pass.  
**Evidence:** _not yet run_

### T410 — Cost models

**Status:** TODO  
**Acceptance:** zero/fixed/per-share/bps commission; spread and bps slippage; decomposition exact within rounding policy.  
**Evidence:** _not yet run_

### T420 — Fill engine

**Status:** TODO  
**Acceptance:** next-open market, limit improvement, gap-through stop, bracket activation, same-bar policies, expiry, and deterministic ordering tested.  
**Evidence:** _not yet run_

### T430 — Risk manager

**Status:** TODO  
**Acceptance:** risk-per-trade formula, fixed sizing modes, exposure/cash/participation caps, daily loss/trade lockouts, reason codes, and protective-exit exception tests.  
**Evidence:** _not yet run_

### T440 — Single-symbol engine

**Status:** TODO  
**Acceptance:** exact event sequence from design; no same-bar signal fill; deterministic rerun; failure retains diagnostics.  
**Evidence:** _not yet run_

### T450 — Multi-symbol engine

**Status:** TODO  
**Acceptance:** timestamp merge, symbol ordering, shared capital, simultaneous intent allocation, and symbol-order-independent economic result under declared allocator.  
**Evidence:** _not yet run_

### T460 — Session liquidation

**Status:** TODO  
**Acceptance:** normal and early close; forced exits tagged; strategy cannot exploit same-close information.  
**Evidence:** _not yet run_

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
