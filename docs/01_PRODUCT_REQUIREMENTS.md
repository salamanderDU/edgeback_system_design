# 01 — Product Requirements

## 1. Problem statement

Intraday strategy research often becomes unreliable because ticker symbols, provider assumptions, feature calculations, execution timing, and cost models are mixed into one script. This makes it difficult to change instruments, compare strategies, reproduce results, or distinguish a real edge from look-ahead and overfitting.

EdgeBack must separate these concerns and provide a repeatable research workflow that an AI coding agent can implement and maintain.

## 2. Primary user

A technically capable individual researcher who:

- writes or asks an AI to write Python;
- wants to test day-trading hypotheses across different stocks/ETFs;
- initially relies on free intraday data;
- needs clear project checkpoints so work can continue across AI context limits;
- may later replace the free provider with paid consolidated data without rewriting strategies or the engine.

## 3. Product goals

### G1 — Config-driven instruments

A user can change one or many symbols in YAML or with CLI overrides. No core or strategy code change is required.

### G2 — Isolated strategies

Each strategy is implemented in its own Python module and registered through a stable interface. Adding a strategy must not require editing the backtest engine.

### G3 — Causal event-driven simulation

The engine processes completed bars in chronological order. Strategy code cannot access future bars. Orders are filled according to an explicit execution model.

### G4 — Realistic enough for first-pass day-trade research

Every run supports configurable spread, slippage, commission, position sizing, stops, targets, daily loss limits, entry cutoffs, and forced end-of-session liquidation.

### G5 — Reproducibility

A completed run can be reproduced from its resolved configuration, canonical dataset/data manifest, code revision, dependency versions, and random seed.

### G6 — Edge-validation workflow

The system supports train/validation/test separation, session-based walk-forward analysis, parameter sweeps, cost stress, robustness analysis, and an immutable experiment record.

### G7 — AI-resumable development

`TASK.md` holds the durable backlog. `STATUS.md` contains the current checkpoint and exact next action. `DECISIONS.md` records architectural changes.

## 4. Non-goals for MVP

- Live trading or broker order routing
- Tick-by-tick, quote, Level 2, or order-book simulation
- Options, futures, FX, or multi-currency accounting
- Historical point-in-time universe construction
- Guaranteed borrow availability or locate fees for short selling
- Corporate-action-perfect institutional data
- Machine-learning model training infrastructure
- Distributed backtesting
- A graphical strategy editor
- A claim that any included strategy is profitable

## 5. Initial market scope

- Instruments: US-listed common stocks and ETFs
- Session: Regular Trading Hours by default; extended hours may be enabled only when provider coverage and config are explicit
- Exchange calendar: XNYS-compatible calendar for holidays, early closes, and daylight saving
- Timeframes: 1 minute, 5 minutes, and 15 minutes; default 5 minutes
- Position mode: long and short supported by the simulator; short results carry an explicit borrow-availability limitation
- Capital: one base currency, USD

The domain model must not prevent additional markets later, but MVP behavior is defined only for the scope above.

## 6. Functional requirements

### FR-001 Configuration

- Load YAML into validated, immutable Pydantic models.
- Resolve defaults, environment-based secrets, and CLI overrides.
- Reject unknown keys by default.
- Persist the fully resolved config for every run.
- Exactly one date-range mode is allowed: explicit `start/end` or rolling lookback.

### FR-002 Symbol handling

- Accept one or many canonical symbols.
- Normalize case and whitespace.
- Maintain a provider-symbol mapping layer for symbols such as share classes.
- Never place a tradable symbol literal in engine logic.
- Record canonical and provider symbols in the data manifest.

### FR-003 Data acquisition

- Separate `data download` from `backtest run`.
- Support provider adapters for yfinance, Alpaca IEX, and local CSV/Parquet.
- Cache raw responses when practical and always store canonical bars in Parquet.
- Respect provider limits with bounded retries and backoff.
- Never silently switch providers.

### FR-004 Data validation

Validate schema, timezone, uniqueness, sorting, OHLC invariants, nonnegative volume, session membership, incomplete bars, expected gaps, provider/feed consistency, and requested coverage. Produce a machine-readable validation report.

### FR-005 Strategy plugins

- One strategy per file.
- Typed parameter model for each strategy.
- Stable lifecycle hooks and read-only context.
- Strategy emits order intents; it cannot mutate cash, positions, fills, or reports.
- Strategy declares warmup and required data.

### FR-006 Backtest engine

- Deterministic chronological event loop across one or many symbols.
- Bar-close signal timing and next-bar execution by default.
- Explicit market, limit, stop, and bracket behavior.
- Explicit policy for stop and target touched in the same bar.
- End-of-session liquidation.
- Shared capital and deterministic allocation for simultaneous orders.

### FR-007 Risk and sizing

- Fixed quantity, fixed notional, percentage of equity, and risk-per-trade sizing.
- Maximum position size, gross exposure, concurrent positions, trades per day, and daily loss.
- Optional long-only or short-enabled mode.
- Reject or resize invalid intents with a recorded reason.

### FR-008 Costs

- Commission models: zero, fixed per order, per share with minimum, and basis points.
- Synthetic spread model because free OHLCV bars generally lack quotes.
- Slippage model: basis points and optional volume participation impact.
- Cost stress multipliers.

### FR-009 Results and reports

Persist orders, fills, trades, positions/equity, daily returns, metrics, warnings, and an HTML report. Include performance by symbol, side, weekday, time bucket, and research split where applicable.

### FR-010 Experiment registry

Assign an immutable run ID. Store run metadata in SQLite and mirror critical metadata in the run directory so results remain readable without the registry.

### FR-011 Research commands

Support parameter sweeps and walk-forward evaluation. Split by trading session, not arbitrary rows. Warmup bars may precede a test window, but fit/selection may not use test outcomes.

### FR-012 Project state

AI implementation work must update `TASK.md` and `STATUS.md` according to `AGENTS.md`.

## 7. Non-functional requirements

### NFR-001 Determinism

Given identical code, canonical data, resolved config, and seed, output trades and metrics must be identical.

### NFR-002 Testability

The core engine, fill model, risk manager, and metrics must run entirely against small local fixtures without network access.

### NFR-003 Extensibility

New providers, strategies, calendars, execution models, and reporters are added behind interfaces rather than conditionals spread through the engine.

### NFR-004 Explainability

Every rejected order, forced exit, data exclusion, repair, warning, and research gate must be visible in artifacts.

### NFR-005 Operational safety

No secrets in the repository or artifacts. No arbitrary code evaluation from config. Backtest commands do not make network calls unless explicitly requested.

### NFR-006 Performance target

The MVP should process roughly one million bar events on a normal developer laptop without exhausting 2 GB of memory. This is an engineering target, not a portable CI pass/fail threshold. Correctness has priority over vectorization.

## 8. Core user stories

1. As a researcher, I can replace `NVDA` with `AAPL` in YAML and run the same strategy without editing Python.
2. As a researcher, I can place a new strategy in one file, register it, and see it in `edgeback strategies list`.
3. As a researcher, I can download recent free data once and rerun many offline backtests against the same checksum.
4. As a researcher, I can see whether a signal filled on the next open, what cost was charged, and why an order was rejected.
5. As a researcher, I can compare in-sample, out-of-sample, and stressed-cost results without overwriting prior runs.
6. As a future AI agent, I can read `STATUS.md` and continue from the exact unfinished step.

## 9. Product-level acceptance

The MVP is accepted only when the workflow below succeeds from a clean checkout using local fixture data, and an optional network workflow succeeds when credentials/data access are available:

```bash
edgeback doctor
edgeback strategies list
edgeback data validate -c configs/example_backtest.yaml --fixture
edgeback backtest run -c configs/example_backtest.yaml --fixture
pytest
```

The generated run must contain a resolved config, data manifest, deterministic trade results, cost-inclusive metrics, warnings, and an HTML report. A second identical run must produce the same canonical outputs except for run ID and timestamps.
