# 02 — Architecture

## 1. Architectural style

EdgeBack is a modular monolith with hexagonal boundaries around market data, calendars, execution, storage, and reporting. The simulation core is event-driven and deterministic. pandas is used for input/output and analysis, while the engine iterates causally through bar events.

The project intentionally avoids starting with a generic third-party backtesting engine. A small custom core makes timing rules, same-bar ambiguity, and artifacts explicit and testable. Provider and strategy interfaces preserve the option to replace components later.

## 2. System context

```text
Free/Local Data Sources
        |
        v
Data Provider Adapters --> Raw Cache --> Normalizer/Validator --> Canonical Parquet
                                                                  |
                                                                  v
YAML/CLI --> Config Resolver --> Backtest Orchestrator --> Event Engine
                                                |             |      |
                                                |             |      +--> Strategy Plugins
                                                |             +---------> Risk + Execution Simulator
                                                v
                                         Run Artifact Writer --> SQLite Registry + HTML Report
```

Data acquisition and simulation are separate processes. A backtest consumes an immutable canonical dataset referenced by a manifest; it does not fetch data implicitly.

## 3. Proposed repository layout

```text
edgeback/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── PROJECT_MANIFEST.yaml
├── TASK.md
├── STATUS.md
├── DECISIONS.md
├── .env.example
├── configs/
│   ├── example_backtest.yaml
│   └── example_sweep.yaml
├── strategy_specs/
├── strategies/
│   ├── __init__.py
│   ├── opening_range_breakout.py
│   ├── vwap_mean_reversion.py
│   └── gap_momentum.py
├── src/edgeback/
│   ├── __init__.py
│   ├── cli.py
│   ├── config/
│   │   ├── models.py
│   │   ├── loader.py
│   │   └── overrides.py
│   ├── domain/
│   │   ├── bars.py
│   │   ├── orders.py
│   │   ├── fills.py
│   │   ├── positions.py
│   │   └── events.py
│   ├── data/
│   │   ├── interfaces.py
│   │   ├── repository.py
│   │   ├── normalization.py
│   │   ├── validation.py
│   │   ├── manifest.py
│   │   └── providers/
│   │       ├── yfinance_provider.py
│   │       ├── alpaca_provider.py
│   │       └── local_file_provider.py
│   ├── calendar/
│   │   ├── interfaces.py
│   │   └── xnys.py
│   ├── strategy/
│   │   ├── base.py
│   │   ├── context.py
│   │   ├── registry.py
│   │   └── intents.py
│   ├── features/
│   │   ├── rolling.py
│   │   ├── atr.py
│   │   └── vwap.py
│   ├── engine/
│   │   ├── clock.py
│   │   ├── event_loop.py
│   │   ├── orchestrator.py
│   │   └── state.py
│   ├── execution/
│   │   ├── broker.py
│   │   ├── fill_models.py
│   │   ├── costs.py
│   │   └── ambiguity.py
│   ├── risk/
│   │   ├── manager.py
│   │   ├── sizing.py
│   │   └── limits.py
│   ├── portfolio/
│   │   ├── ledger.py
│   │   └── accounting.py
│   ├── metrics/
│   │   ├── performance.py
│   │   ├── trades.py
│   │   └── robustness.py
│   ├── research/
│   │   ├── splits.py
│   │   ├── sweep.py
│   │   ├── walk_forward.py
│   │   └── bootstrap.py
│   ├── artifacts/
│   │   ├── writer.py
│   │   ├── registry.py
│   │   └── schemas.py
│   └── reporting/
│       ├── html.py
│       └── charts.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── strategies/
│   └── golden/
├── data/          # ignored; raw and canonical market data
└── runs/          # ignored; immutable generated run folders
```

## 4. Module responsibilities

### Configuration

Parses YAML, validates values, resolves defaults and overrides, and emits a frozen `ResolvedConfig`. No downstream component reads YAML or environment variables directly.

### Data

Provider adapters retrieve provider-native data. Normalization converts it to the canonical bar schema. Validation produces a report. `DataRepository` serves canonical bars and manifests to the engine.

### Calendar

Provides sessions, opens, closes, early closes, and interval boundaries. No component calculates US holidays manually.

### Strategy

Loads trusted local strategy classes, validates parameters, and exposes a read-only causal context. Strategies emit intents only.

### Engine

Owns the clock and event sequence. Coordinates strategy callbacks, risk evaluation, order lifecycle, fills, accounting, and session boundaries.

### Execution

Converts accepted orders to fills using bars and configured cost/ambiguity models. It does not decide whether a strategy should trade.

### Risk

Sizes or rejects intents using portfolio/session state and configured limits. All decisions include reason codes.

### Portfolio

Maintains cash, positions, realized/unrealized P&L, exposure, and equity. Accounting changes occur only through fills and explicit corporate-action events.

### Metrics and reporting

Compute transparent metrics from persisted canonical outputs. Reporting may not alter results.

### Research

Creates session-based splits, launches multiple immutable runs, selects parameters using training/validation only, and aggregates out-of-sample results.

### Artifacts

Generates run IDs, writes atomic run folders, registers metadata, and protects completed runs from overwrite.

## 5. Dependency direction

```text
CLI/Orchestrator
  -> interfaces and domain models
  -> data/calendar/strategy/engine/execution/risk/portfolio
  -> artifact/reporting adapters

Domain models must not import provider, CLI, report, or filesystem code.
Strategy modules may import only public strategy/domain/feature APIs.
Execution and risk may read engine state through typed interfaces, not globals.
```

Circular imports are a design failure. Shared enums/value objects belong under `domain/`.

## 6. Core domain objects

- `Bar`: completed canonical OHLCV interval with start/end UTC times and session metadata
- `OrderIntent`: strategy request before risk validation
- `Order`: accepted/rejected broker-simulation instruction with lifecycle state
- `Fill`: immutable execution event with price, quantity, costs, and reason
- `Position`: quantity, average price, realized/unrealized P&L
- `PortfolioSnapshot`: cash, equity, gross/net exposure at an event time
- `SessionState`: session date, counters, daily P&L, lockout flags
- `StrategyState`: strategy-owned serializable state
- `RunContext`: immutable config, dataset ID, code metadata, seed

Use `Decimal` only where exact fee/cash rounding materially matters; market prices and indicators may use float64. Centralize rounding policy and test it.

## 7. Multi-symbol event ordering

Bars are merged by `bar_end_utc`. For each timestamp:

1. Prepare the bars that end at that timestamp, sorted by canonical symbol.
2. Process orders eligible to execute using those bars in a deterministic order.
3. Apply fills and account updates.
4. Invoke portfolio-level callbacks once, if used.
5. Invoke per-symbol `on_bar` callbacks in canonical symbol order.
6. Risk-check emitted intents as a batch.
7. Queue accepted orders for future execution.
8. Persist the event checkpoint.

When simultaneous orders compete for capital, allocation follows a configured deterministic method. MVP default is `priority_then_symbol`; the report must disclose it. A future `pro_rata` allocator may be added behind the same interface.

## 8. Reproducibility identity

A run identity includes:

- resolved config hash;
- canonical data manifest hash;
- strategy ID/version and parameter hash;
- engine version and Git commit when available;
- dependency lock hash or package-version snapshot;
- random seed;
- execution-model version.

The run folder name may include a timestamp and short hash, but logical equivalence is determined by the identity fields above.

## 9. Atomicity and failure behavior

A run is first written under a temporary directory. It becomes `COMPLETED` only after all required artifacts validate and the directory is atomically renamed. Failed runs retain logs and metadata under a `FAILED` state but may not masquerade as completed.

Completed run artifacts are immutable. Re-running creates a new run ID, even if logically equivalent; the registry may identify it as a duplicate configuration/data identity.

## 10. Extension points

- `MarketDataProvider`
- `TradingCalendar`
- `Strategy`
- `PositionSizer`
- `RiskRule`
- `CommissionModel`
- `SpreadModel`
- `SlippageModel`
- `FillModel`
- `MetricsPlugin`
- `ReportRenderer`
- `ArtifactRegistry`

Each extension point requires a protocol/abstract base, a deterministic reference implementation, and contract tests.
