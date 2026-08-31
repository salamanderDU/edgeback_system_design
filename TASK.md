# TASK.md — Durable Implementation Backlog

Last design update: 2026-08-21  
Allowed states: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`  
Current milestone: M8 — Hardening, documentation, and MVP acceptance
Current task: T830

## Update rules

- Change a task to `IN_PROGRESS` before editing implementation files.
- A `DONE` task must include validation evidence in its detail section.
- When blocked, state the blocker and the smallest unblocking action.
- Update `STATUS.md` at task start, task completion, and before stopping.
- Do not delete completed task history. Add corrective tasks when regressions appear.

## Milestone summary

| Milestone | Name | Status |
|---|---|---|
| M0 | Bootstrap and quality baseline | BLOCKED |
| M1 | Configuration and domain models | DONE |
| M2 | Calendar, data schema, repository, and fixtures | DONE |
| M3 | Strategy contract and ORB plugin | DONE |
| M4 | Event engine, execution, portfolio, and risk | DONE |
| M5 | Metrics, artifacts, registry, and reports | DONE |
| M6 | CLI and free-data adapters | DONE |
| M7 | Sweeps, walk-forward, and robustness | DONE |
| M8 | Hardening, documentation, and MVP acceptance | BLOCKED |

## Task index

| ID | Milestone | Status | Depends on | Deliverable |
|---|---|---|---|---|
| T000 | M0 | DONE | — | Create Python project skeleton and preserve design docs |
| T010 | M0 | BLOCKED | T000 | Configure pytest, Ruff, type checking, and offline CI baseline |
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
| T500 | M5 | DONE | T440 | Implement intents/orders/fills/trades/equity artifact tables |
| T510 | M5 | DONE | T500 | Implement performance/trade/cost metrics with edge cases |
| T520 | M5 | DONE | T500 | Implement atomic run writer, schema validation, and checksums |
| T530 | M5 | DONE | T520 | Implement SQLite run registry and immutable completed runs |
| T540 | M5 | DONE | T510,T520 | Implement HTML report and warning/conclusion sections |
| T600 | M6 | DONE | T110,T230,T340,T440,T520 | Implement Typer CLI and `doctor` |
| T610 | M6 | DONE | T230 | Implement yfinance adapter with explicit capability/limitation metadata |
| T620 | M6 | DONE | T230 | Implement Alpaca IEX adapter with environment-only credentials |
| T630 | M6 | DONE | T600,T610,T620 | Implement data download/validate/list commands and network markers |
| T640 | M6 | DONE | T600,T540 | Implement backtest run/batch, run list/show, and report commands |
| T700 | M7 | DONE | T510,T530,T640 | Implement session-based train/validation/test splits |
| T710 | M7 | DONE | T700 | Implement deterministic parameter sweep and trial registry |
| T720 | M7 | DONE | T710 | Implement anchored/rolling walk-forward orchestration |
| T730 | M7 | DONE | T720 | Implement cost stress, parameter-neighborhood, concentration, bootstrap |
| T740 | M7 | DONE | T730 | Implement research gates and conclusion labels |
| T800 | M8 | BLOCKED | T640,T740 | Run complete offline MVP acceptance scenario |
| T810 | M8 | BLOCKED | T630,T800 | Run optional provider smoke tests and document observed limitations |
| T820 | M8 | DONE | T800 | Finalize user/strategy/provider authoring documentation |
| T830 | M8 | BLOCKED | T800,T820 | Produce release checklist, version 0.1.0, and final safe handoff |

---

## Detailed tasks and acceptance evidence

### T000 — Create Python project skeleton

**Status:** DONE  
**Deliverables:** `pyproject.toml`, `src/edgeback/`, `tests/`, `strategies/`, package/CLI placeholders, design files retained at root.  
**Acceptance:** package imports; no design file is lost; no generated data committed.  
**Evidence:** Created the complete `src/` package, trusted `strategies/`, tests, configs, schemas, docs, CI, templates and benchmark. Package imports and wheel build pass.

### T010 — Quality baseline

**Status:** BLOCKED  
**Acceptance:** `pytest`, `ruff check .`, `ruff format --check .`, and chosen static type checker run on the skeleton; core tests require no network.  
**Evidence:** Pytest and compile/static scans pass, and CI/Ruff/mypy configuration exists. Exact local Ruff/mypy execution is blocked because those tools are unavailable and package-network access is disabled.

### T020 — Operational baseline

**Status:** DONE  
**Acceptance:** structured logging utility, typed application errors, `.env.example`, and ignore rules cover `.env`, `data/`, `runs/`, caches, virtual environments, SQLite runtime files, and provider payloads. Secrets redaction test exists.  
**Evidence:** Implemented typed errors/exit codes, JSONL logging, recursive secret redaction, `.env.example`, and ignore rules. Offline tests cover redaction/logging.

### T100 — Configuration models

**Status:** DONE  
**Acceptance:** models cover all sections in `configs/example_backtest.yaml`; unknown keys fail; cross-field date/risk/order constraints tested; config objects are frozen after resolution.  
**Evidence:** Strict frozen Pydantic models cover the complete example backtest/research configurations, reject unknown keys and validate cross-field constraints.

### T110 — Loader and overrides

**Status:** DONE  
**Acceptance:** documented precedence works; `--symbol` replacement and typed `--param` overrides tested; unsafe YAML tags rejected.  
**Evidence:** Safe YAML loading and typed `--symbol`, `--param`, and `--set` precedence are implemented and tested; unsafe tags fail.

### T120 — Domain models

**Status:** DONE  
**Acceptance:** typed Bar, Intent, Order, Fill, Position, events, reason codes, and statuses serialize deterministically; invalid states rejected.  
**Evidence:** Implemented timezone-aware immutable Bar/Intent/Order/Fill/Position/Trade/events/status/reason models with deterministic serialization and validation.

### T130 — Reproducibility metadata

**Status:** DONE  
**Acceptance:** stable canonical config hash; Git/dependency/seed metadata captured without exposing sensitive host data; dirty tree noted.  
**Evidence:** Implemented canonical config/simulation hashes plus Git, runtime, dependency, seed and execution-model metadata without sensitive host identity.

### T200 — Calendar

**Status:** DONE  
**Acceptance:** normal day, holiday, daylight-saving period, and early-close fixtures; no fixed UTC-offset logic.  
**Evidence:** Implemented XNYS calendar adapter via interface with holiday, DST, normal-session and early-close tests.

### T210 — Bar schema and validation models

**Status:** DONE  
**Acceptance:** matches `schemas/bar.schema.json`; timezone-naive, duplicate, invalid OHLC, incomplete, mixed-feed cases tested.  
**Evidence:** Implemented canonical schema and machine-readable validation reports covering timezone, OHLC, duplicate, incomplete, future and mixed-feed cases.

### T220 — Local provider

**Status:** DONE  
**Acceptance:** imports mapped CSV and Parquet with explicit timestamp semantics/timezone; ambiguous input fails; provider contract tests pass.  
**Evidence:** Implemented explicit local CSV/Parquet import mapping, timestamp semantics/timezone handling and provider contract tests.

### T230 — Repository and manifests

**Status:** DONE  
**Acceptance:** atomic Parquet partitions, deterministic dataset hash, manifest/validation files, no silent provider mixing.  
**Evidence:** Implemented atomic partitioned canonical repository, deterministic dataset identity, manifests, checksums and no provider/feed mixing.

### T240 — Fixtures

**Status:** DONE  
**Acceptance:** tiny single/multi-symbol sessions include normal fills, gaps, ambiguous brackets, missing bars, and early close; expected outputs are human-readable.  
**Evidence:** Implemented deterministic single/multi-symbol full-session fixtures covering breakout, ambiguity, missing data and early close mechanics.

### T300 — Strategy contract and registry

**Status:** DONE  
**Acceptance:** trusted registry, strict parameter models, lifecycle hooks, read-only context, serializable state, and contract tests.  
**Evidence:** Implemented strategy base/context/metadata, strict params, trusted registry, lifecycle hooks and serializable state.

### T310 — Causal history

**Status:** DONE  
**Acceptance:** context cannot return data after engine time; future mutation sentinel passes.  
**Evidence:** Causal history is clipped at engine time; future mutation and copy/isolation tests pass.

### T320 — Feature helpers

**Status:** DONE  
**Acceptance:** causal opening range, ATR/true range, session VWAP or volume ratio helpers needed by ORB; boundary tests.  
**Evidence:** Implemented causal true range/ATR, median volume ratio, opening range and session VWAP helpers with tests.

### T330 — ORB strategy

**Status:** DONE  
**Acceptance:** implements `strategy_specs/opening_range_breakout.yaml`; no ticker literals; session reset, cutoff, one-trade controls, stop/target intents, and golden test pass.  
**Evidence:** Implemented ORB 0.1.0 from the hypothesis card, including reset/cutoff/volume/range/bracket rules and no-look-ahead tests.

### T340 — Strategy services

**Status:** DONE  
**Acceptance:** list/describe returns deterministic metadata and parameter schema; duplicate ID/version conflict fails.  
**Evidence:** Implemented deterministic list/describe services and parameter schemas for all three trusted seed strategies.

### T400 — Portfolio ledger

**Status:** DONE  
**Acceptance:** long/short accounting, fees, mark-to-market, realized/unrealized P&L, exposure, and reconciliation invariants pass.  
**Evidence:** Implemented FIFO long/short ledger, cash/equity/P&L/exposure/cost accounting, leverage guards and reconciliation tests.

### T410 — Cost models

**Status:** DONE  
**Acceptance:** zero/fixed/per-share/bps commission; spread and bps slippage; decomposition exact within rounding policy.  
**Evidence:** Implemented zero/fixed/per-share/bps commissions, synthetic spread and slippage with exact per-fill decomposition.

### T420 — Fill engine

**Status:** DONE  
**Acceptance:** next-open market, limit improvement, gap-through stop, bracket activation, same-bar policies, expiry, and deterministic ordering tested.  
**Evidence:** Implemented market/limit/stop/bracket lifecycle, limit improvement, gap-through, expiry, OCO and all ambiguity policies.

### T430 — Risk manager

**Status:** DONE  
**Acceptance:** risk-per-trade formula, fixed sizing modes, exposure/cash/participation caps, daily loss/trade lockouts, reason codes, and protective-exit exception tests.  
**Evidence:** Implemented all sizing modes, stable allocation, cash/exposure/participation limits, daily lockouts, cooldown and reason codes.

### T440 — Single-symbol engine

**Status:** DONE  
**Acceptance:** exact event sequence from design; no same-bar signal fill; deterministic rerun; failure retains diagnostics.  
**Evidence:** Implemented deterministic causal single-symbol event lifecycle with next-bar fills, warmup suppression, callbacks and retained failure diagnostics.

### T450 — Multi-symbol engine

**Status:** DONE  
**Acceptance:** timestamp merge, symbol ordering, shared capital, simultaneous intent allocation, and symbol-order-independent economic result under declared allocator.  
**Evidence:** Implemented multi-symbol timestamp merge, canonical ordering, shared capital and globally chronological event normalization.

### T460 — Session liquidation

**Status:** DONE  
**Acceptance:** normal and early close; forced exits tagged; strategy cannot exploit same-close information.  
**Evidence:** Implemented tagged session-close liquidation using final calendar bar, including explicit XNYS early-close test and no same-close strategy exploit.

### T500 — Canonical result tables

**Status:** DONE  
**Acceptance:** complete linkage among intents/orders/fills/trades; Parquet schemas stable; reason and cost fields present.  
**Evidence:** Implemented stable intents/decisions/orders/events/fills/trades/equity/warnings schemas, linkage validation and deterministic table projection.

### T510 — Metrics

**Status:** DONE  
**Acceptance:** manual fixtures and zero/undefined cases; units and observation counts; `null` plus reason for undefined.  
**Evidence:** Implemented cost-inclusive metrics, drawdown, daily Sharpe/Sortino, trade statistics, breakdowns and null-plus-reason undefined values.

### T520 — Run writer

**Status:** DONE  
**Acceptance:** temp-to-final atomic transition, required artifacts/schema/checksum validation, `FAILED` diagnostics, no overwrite.  
**Evidence:** Implemented temp-to-final run writer, required artifacts, schema/checksum validation, failed diagnostics and overwrite refusal.

### T530 — Registry

**Status:** DONE  
**Acceptance:** SQLite records logical identity, state, paths, parent/fold links; registry loss does not make run folders unreadable.  
**Evidence:** Implemented SQLite registry with logical identity, paths and parent/fold links; run folders remain independently readable.

### T540 — HTML report

**Status:** DONE  
**Acceptance:** all required sections, limitations/warnings, cost-inclusive figures, conclusion label; report generation does not alter metrics.  
**Evidence:** Implemented self-contained HTML report with identity, data limitations, assumptions, summary, equity, costs, breakdowns, gates and warnings.

### T600 — CLI and doctor

**Status:** DONE  
**Acceptance:** command surface and exit codes match design; `doctor` redacts secrets and works offline.  
**Evidence:** Implemented Typer command surface and offline `doctor` with secret-safe provider-auth presence reporting.

### T610 — yfinance adapter

**Status:** DONE  
**Acceptance:** explicit interval/session/adjustment arguments, recent-lookback validation, cache/manifest metadata, bounded retries, mocked tests plus optional smoke test.  
**Evidence:** Implemented yfinance adapter with explicit arguments, bounded lookback, capability metadata, lazy dependency and mocked tests.

### T620 — Alpaca IEX adapter

**Status:** DONE  
**Acceptance:** environment-only keys, explicit `feed=iex`, capability warning, pagination/rate handling, mocked tests plus optional smoke test.  
**Evidence:** Implemented Alpaca IEX adapter with environment-only keys, explicit feed, pagination/retry metadata and mocked tests.

### T630 — Data CLI

**Status:** DONE  
**Acceptance:** provider list, download, import, validate, and dataset list; no provider fallback; meaningful exit codes.  
**Evidence:** Implemented provider list, download, local import, validate and dataset list commands with no implicit fallback.

### T640 — Backtest/run CLI

**Status:** DONE  
**Acceptance:** run/batch and run/report inspection; symbol/parameter overrides; final artifact path; offline missing-data failure.  
**Evidence:** Implemented run/batch, symbol/param overrides, runs list/show and derived report commands; backtests remain offline by default.

### T700 — Research splits

**Status:** DONE  
**Acceptance:** chronological session splits, warmup isolation, embargo, immutable final test.  
**Evidence:** Implemented chronological complete-session train/validation/test splits, embargo and causal warmup-only history.

### T710 — Sweep

**Status:** DONE  
**Acceptance:** bounded deterministic grid/random trials, all trials persisted, no final-test selection.  
**Evidence:** Implemented bounded deterministic grid/random sweeps and atomic per-trial persistence; selection uses validation only.

### T720 — Walk-forward

**Status:** DONE  
**Acceptance:** rolling/anchored folds, fit/select in train only, concatenated OOS trades, fold metadata.  
**Evidence:** Implemented rolling/anchored walk-forward folds, fold selection and concatenated OOS artifacts.

### T730 — Robustness

**Status:** DONE  
**Acceptance:** cost multipliers, delayed entry, parameter neighborhood, concentration, session bootstrap with seed.  
**Evidence:** Implemented cost/delay stress, parameter stability indicator, best-trade/session concentration and seeded session bootstrap.

### T740 — Gates/conclusions

**Status:** DONE  
**Acceptance:** gate configuration, reasons, and allowed conclusion labels; no language implying guaranteed edge.  
**Evidence:** Implemented configurable promotion gates and only the six allowed uncertainty-aware conclusion labels.

### T800 — Offline MVP acceptance

**Status:** BLOCKED  
**Acceptance:** all ten scenarios in `docs/08_TESTING_AND_ACCEPTANCE.md` pass from clean environment; evidence and artifact hashes recorded.  
**Evidence:** All functional offline acceptance commands and 56 offline tests pass, including deterministic canonical-output hashes. Exact Ruff/mypy and genuine PyArrow gates remain environment-blocked.

### T810 — Provider smoke tests

**Status:** BLOCKED  
**Acceptance:** tiny yfinance/Alpaca tests when access is available; observed capabilities and limitations documented; task may be `BLOCKED` without credentials but cannot block offline MVP.  
**Evidence:** Mocked provider tests and opt-in marked live smoke tests are included. Live execution is blocked by disabled network and absent Alpaca credentials.

### T820 — Documentation

**Status:** DONE  
**Acceptance:** install/use, data import, strategy authoring, provider authoring, artifact interpretation, research workflow, and troubleshooting are accurate against version 0.1.0.  
**Evidence:** Completed install/use, import, strategy/provider authoring, artifacts/research and troubleshooting guides matched to version 0.1.0.

### T830 — Release/handoff

**Status:** BLOCKED  
**Acceptance:** version 0.1.0, release checklist, clean status, all quality gates, safe `STATUS.md` handoff, known limitations listed.  
**Evidence:** Version 0.1.0, changelog, license, release checklist, wheel/source release and safe handoff are prepared. Final release gate remains blocked only on unavailable Ruff/mypy/PyArrow validation.

