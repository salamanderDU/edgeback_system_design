# EdgeBack System Design — Combined Reference

> Generated from the modular authoritative files. The modular files remain the source of truth.



---

## Source file: `README.md`

# EdgeBack — ชุดเอกสารออกแบบระบบ Backtest สำหรับหา Intraday Edge

> สถานะปัจจุบัน: **ออกแบบระบบเสร็จแล้ว แต่ยังไม่ได้เขียนตัวโปรแกรมจริง**

EdgeBack ถูกออกแบบให้เป็นระบบ backtest แบบ event-driven ด้วย Python สำหรับหุ้นและ ETF โดยเปลี่ยนหุ้นได้จากไฟล์ config และแยกกลยุทธ์ออกเป็นคนละไฟล์อย่างชัดเจน เหมาะสำหรับให้ AI CLI เช่น Codex CLI, Claude Code, Gemini CLI หรือ agent ใน IDE อ่านเอกสารทั้งชุดแล้วค่อยสร้างระบบตามลำดับงาน

## สิ่งสำคัญที่ชุดนี้กำหนดไว้แล้ว

- เปลี่ยนหุ้นจาก `symbols:` ใน YAML หรือใช้ `--symbol` โดยไม่แก้โค้ด engine
- กลยุทธ์ทุกตัวอยู่คนละไฟล์ เช่น `strategies/opening_range_breakout.py`
- ใช้ backtest แบบเดินทีละแท่ง เพื่อควบคุม look-ahead bias และลำดับการ fill
- สัญญาณที่สร้างจากราคาปิดของแท่งหนึ่ง จะเข้าซื้อ/ขายได้เร็วที่สุดที่แท่งถัดไป
- จำลอง spread, slippage, commission, stop loss, take profit และกรณี stop/target ถูกแตะในแท่งเดียวกัน
- ปิดสถานะก่อนหรือเมื่อจบ session โดยค่าเริ่มต้น เพื่อให้เป็น day trade
- แยกขั้นตอน download data ออกจากการ backtest ทำให้รันซ้ำแบบ offline ได้
- เก็บข้อมูลเป็น Parquet และเก็บผลแต่ละรันแบบ immutable พร้อม config, checksum, trade log และ report
- มีขั้นตอน walk-forward, out-of-sample และ stress test ก่อนเรียกผลว่าเป็น edge
- มี `TASK.md` และ `STATUS.md` เพื่อให้ AI ตัวใหม่ resume งานต่อได้เมื่อ session เดิมติดลิมิต

## วิธีส่งให้ AI CLI

1. แตกไฟล์ ZIP แล้วเปิดโฟลเดอร์นี้เป็น project root
2. ส่งข้อความจาก `AI_CLI_PROMPT.txt` ให้ AI CLI
3. ให้ AI อ่าน `PROJECT_MANIFEST.yaml` และ `AGENTS.md` ก่อน
4. AI จะเริ่มจาก task แรกใน `TASK.md` และต้องอัปเดต `TASK.md`/`STATUS.md` ระหว่างทำงาน

ไฟล์หลักที่มนุษย์ควรรู้จัก:

- `PROJECT_MANIFEST.yaml` — ลำดับอ่านและข้อกำหนดระดับโครงการ
- `AGENTS.md` — กติกาบังคับสำหรับ AI ที่เขียนโค้ด
- `docs/` — requirements, architecture, data, engine, strategy, research และ testing
- `strategy_specs/` — นิยามกลยุทธ์ตั้งต้น แยกคนละไฟล์
- `configs/` — ตัวอย่าง config สำหรับ backtest และ parameter sweep
- `TASK.md` — backlog และหลักฐานว่า task ไหนเสร็จแล้ว
- `STATUS.md` — checkpoint ล่าสุดและคำสั่ง/งานถัดไปที่ต้องทำ
- `DECISIONS.md` — บันทึกการตัดสินใจทางสถาปัตยกรรม

## ตัวอย่างแนวคิดการเปลี่ยนหุ้นหลังระบบถูกสร้าง

```yaml
data:
  symbols: [NVDA]
  interval: 5m

strategy:
  name: opening_range_breakout
```

เปลี่ยนเป็น:

```yaml
data:
  symbols: [AAPL, MSFT, AMZN]
```

หรือใช้ CLI override โดยไม่แตะไฟล์กลยุทธ์:

```bash
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL
```

## ขอบเขต MVP

- ตลาดเริ่มต้น: หุ้นและ ETF สหรัฐ
- Session เริ่มต้น: Regular Trading Hours
- Timeframe: 1m, 5m และ 15m โดย 5m เป็นค่าเริ่มต้น
- รองรับ long/short ในโมเดล แต่ข้อมูลฟรีไม่สามารถรับรอง borrow availability ของการ short
- ข้อมูลเริ่มต้น: `yfinance` สำหรับทดลองช่วงล่าสุด และ Alpaca Basic/IEX สำหรับประวัติที่ยาวกว่า
- รองรับ CSV/Parquet ที่ผู้ใช้นำมาเองตั้งแต่ต้น เพื่ออัปเกรดไปสู่ข้อมูลเสียเงินภายหลังโดยไม่เปลี่ยน engine
- ยังไม่รวม live trading, options, tick data, Level 2, broker routing หรือการเลือก universe ย้อนหลังแบบไร้ survivorship bias

## ข้อจำกัดของข้อมูลฟรี

ข้อมูล intraday ฟรีมีข้อจำกัดด้านช่วงเวลา ความครบถ้วนของตลาด rate limit และสิทธิ์การใช้งาน จึงต้องบันทึก provider/feed ในทุก experiment และห้ามเอาผลจากคนละ feed มาเทียบกันโดยไม่ระบุ ระบบนี้สร้างเพื่อการวิจัย ไม่ใช่หลักฐานว่ากลยุทธ์จะทำกำไรจริง


---

## Source file: `AGENTS.md`

# AGENTS.md — Mandatory Operating Contract for AI Coding Agents

## 1. Mission

Implement **EdgeBack**, a deterministic Python intraday backtesting and edge-research system. A user must be able to change a stock symbol, date range, timeframe, cost model, and strategy parameters through YAML or CLI overrides without editing engine code. Every strategy must live in a separate Python file and interact with the engine only through the documented strategy contract.

This repository starts as a **design package**, not a completed application. Build it incrementally from `TASK.md`.

## 2. Mandatory read sequence

Before changing code, read `PROJECT_MANIFEST.yaml`, then every file in its `read_order`. Do not recursively read market data, generated reports, virtual environments, caches, or `runs/` unless a task specifically requires them.

## 3. State and resume protocol

`TASK.md` and `STATUS.md` are mandatory, not optional documentation.

At the beginning of every work session:

1. Read `TASK.md`, `STATUS.md`, and `DECISIONS.md`.
2. Inspect the working tree and existing tests.
3. Confirm the current task or select the first unblocked `TODO` task whose dependencies are `DONE`.
4. Change that task to `IN_PROGRESS` in `TASK.md` **before** implementation.
5. Update the header and current objective in `STATUS.md`.

At every checkpoint, and always before context exhaustion or stopping:

1. Save all code and tests.
2. Run the narrowest relevant validation commands.
3. Update the task status and record evidence in `TASK.md`.
4. Rewrite `STATUS.md` as an accurate snapshot containing:
   - current task and exact implementation state;
   - files changed;
   - tests/commands run and their result;
   - blockers or unresolved assumptions;
   - the **exact next action**, preferably including the next command or file;
   - whether the working tree is safe to resume.
5. Record architectural changes in `DECISIONS.md` before relying on them.

A future agent must be able to resume by reading only `PROJECT_MANIFEST.yaml`, `AGENTS.md`, `TASK.md`, `STATUS.md`, and the relevant design document.

## 4. Task lifecycle

Allowed states are exactly: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.

A task is `DONE` only when its acceptance criteria are met and validation evidence is recorded. Code existing is not sufficient. Do not mark a task done when tests are failing, the implementation is stubbed, or an acceptance criterion was silently deferred.

Work in small vertical slices. Prefer completing one task with tests over partially editing many modules.

## 5. Design rules that must not be violated

- Core code must never contain a hard-coded tradable symbol.
- Strategy modules may not fetch data, read secrets, write reports, or mutate portfolio state directly.
- Signals created from a completed bar may fill no earlier than the next bar, except engine-generated session-close liquidation.
- All timestamps are timezone-aware. Storage is UTC; exchange-session logic uses `America/New_York` for the initial US-equity scope.
- Backtests are offline and deterministic by default. Data acquisition is a separate command.
- Every run writes a resolved configuration, data manifest, code/version metadata, random seed, trades, orders, equity, metrics, warnings, and logs.
- Missing bars, duplicate bars, mixed feeds, incomplete bars, invalid OHLC, and timezone ambiguity must produce explicit validation results. Never silently repair data unless a named repair policy is enabled and recorded.
- The fill model, spread, slippage, commissions, and same-bar ambiguity policy must be explicit in each run.
- A strategy is a research hypothesis until it passes out-of-sample and robustness checks. Reports must not label in-sample profitability as a proven edge.
- Secrets belong in environment variables or an untracked `.env`; never write keys to config, logs, reports, tests, or commits.

## 6. Implementation conventions

- Use a `src/` package layout and `pyproject.toml`.
- Target Python 3.12. Avoid relying on implementation-specific behavior.
- Use typed domain models and Pydantic for configuration validation.
- Use pandas for the MVP and Parquet for canonical bar/result data.
- Use dependency inversion: providers, repositories, execution models, calendars, and reporters must implement interfaces consumed by the engine.
- Keep provider-specific logic under `src/edgeback/data/providers/`.
- Keep user strategies under the top-level `strategies/` package, one strategy per file.
- Keep pure, reusable indicators under `src/edgeback/features/`.
- Use structured logging. User-facing CLI output should be concise; full details go to run logs.
- Do not use `eval`, `exec`, dynamic code generated from YAML, or unsafe YAML loaders.
- Do not add a heavy framework when a small typed component is enough.

## 7. Required quality gates

Before completing a task, run the tests that cover it. Before completing a milestone, run at least:

```bash
pytest
ruff check .
ruff format --check .
```

Run the configured static type checker once it exists. Network tests must be opt-in and marked separately. Core tests must run without API keys and without internet access.

## 8. Change control

The numbered design files define the intended system. When implementation pressure reveals a conflict:

1. Do not silently change behavior.
2. Add or update an ADR in `DECISIONS.md` with context, decision, alternatives, and consequences.
3. Update the affected design document and task acceptance criteria.
4. Mention the change in `STATUS.md`.

## 9. Definition of a safe handoff

A handoff is safe only when:

- no file is left half-written;
- the active task status is truthful;
- failed tests are listed with the observed error;
- the exact next step is documented;
- secrets are absent;
- generated data and run artifacts are not accidentally staged;
- another agent can continue without asking the user to repeat project requirements.


---

## Source file: `docs/01_PRODUCT_REQUIREMENTS.md`

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


---

## Source file: `docs/02_ARCHITECTURE.md`

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


---

## Source file: `docs/03_DATA_LAYER.md`

# 03 — Data Layer

## 1. Principles

1. Provider-native data is not engine data.
2. Fetching, normalization, validation, and simulation are separate steps.
3. A dataset has a stable ID and manifest.
4. No provider or feed is silently substituted.
5. No OHLCV gap is silently forward-filled.
6. Every timestamp has explicit timezone semantics.
7. A backtest is offline by default.

## 2. Provider interface

A provider adapter implements behavior equivalent to:

```python
class MarketDataProvider(Protocol):
    provider_id: str

    def describe_capabilities(self) -> ProviderCapabilities: ...
    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol: ...
    def fetch_bars(self, request: BarRequest) -> RawBarBatch: ...
    def fetch_actions(self, request: ActionRequest) -> RawActionBatch: ...
```

`BarRequest` includes symbols, interval, exact UTC/local range, session inclusion, adjustment request, feed, and paging controls. Provider retries are bounded and recorded. Rate-limit sleeps must be observable in logs.

Provider adapters may not write directly into canonical storage. They return raw batches plus metadata to the ingestion service.

## 3. Storage zones

```text
data/
├── raw/<provider>/<request_id>/
│   ├── payload.*
│   └── request_metadata.json
├── canonical/bars/
│   └── provider=<id>/feed=<id>/interval=<n>/symbol=<ticker>/year=<yyyy>/month=<mm>/*.parquet
├── manifests/<dataset_id>.json
└── validation/<dataset_id>.json
```

The raw zone is optional for providers whose terms or response format make storage inappropriate, but request metadata remains mandatory. The canonical zone is required.

Canonical files are append-safe and deduplicated by `(symbol, interval, bar_start_utc)`. Ingestion must write temporary files and atomically replace partitions.

## 4. Canonical bar schema

The authoritative machine-readable schema is `schemas/bar.schema.json`. Parquet should use these logical meanings:

| Field | Type | Required | Meaning |
|---|---:|:---:|---|
| `symbol` | string | yes | Canonical symbol, uppercase |
| `provider_symbol` | string | yes | Symbol sent to provider |
| `interval_seconds` | int32 | yes | Bar duration |
| `bar_start_utc` | timestamp UTC | yes | Inclusive interval start |
| `bar_end_utc` | timestamp UTC | yes | Exclusive interval end; strategy event time |
| `session_date` | date | yes | Exchange-local trading date |
| `session_type` | enum | yes | `regular`, `pre`, `post`, or `overnight` |
| `open/high/low/close` | float64 | yes | Normalized price fields |
| `volume` | int64 | yes | Nonnegative provider-reported volume |
| `vwap` | float64 nullable | no | Provider-reported or null; never silently synthesized |
| `trade_count` | int64 nullable | no | Provider-reported count or null |
| `is_complete` | bool | yes | Incomplete current bar must not be used |
| `source_provider` | string | yes | Provider ID |
| `source_feed` | string | yes | Feed ID such as `yahoo` or `iex` |
| `adjustment_mode` | enum | yes | `raw`, `split_adjusted`, or explicitly named mode |
| `ingested_at_utc` | timestamp UTC | yes | Acquisition timestamp |

`bar_end_utc - bar_start_utc` must equal `interval_seconds`. A strategy receives a bar only at `bar_end_utc` and only when `is_complete=true`.

## 5. Dataset manifest

Every canonical dataset has a JSON manifest containing at least:

- dataset ID and schema version;
- provider and feed;
- provider capability snapshot;
- canonical/provider symbols;
- interval and requested/actual coverage;
- session types included;
- exchange calendar ID and version metadata when available;
- adjustment mode and corporate-action handling;
- row counts per symbol/session;
- missing/duplicate/invalid bar counts;
- raw request IDs;
- partition checksums and aggregate hash;
- ingestion code version and timestamp;
- validation result and warnings;
- licensing/usage warning applicable to the provider.

A backtest references one or more compatible dataset IDs. Mixed providers/feeds require an explicit multi-dataset research plan and are forbidden inside a single symbol series.

## 6. Timezone and session rules

- Persist UTC timestamps.
- Convert through a calendar service, not fixed UTC offsets.
- US session decisions use `America/New_York` and an XNYS-compatible calendar.
- Handle holidays, daylight saving, and early closes from the calendar.
- Never create bars across a session boundary.
- When resampling 1m data to 5m/15m, group within a session and require a configured completeness threshold. Default: all expected component bars must exist.
- Drop or quarantine the latest provider bar when it is not complete.

## 7. Corporate actions and adjustments

Provider defaults must never be trusted implicitly. Each adapter passes explicit adjustment arguments and records the observed mode.

MVP policy:

- Prefer split-adjusted intraday bars for long history so splits do not create artificial gaps.
- Do not dividend-adjust intraday execution prices unless the provider supplies only a combined adjusted series and the limitation is documented.
- Preserve raw provider fields when allowed.
- When adjustment provenance is ambiguous, validation fails rather than guessing.
- Do not combine raw and adjusted partitions.

Because day trades close within a session, dividends rarely affect an individual trade, but inconsistent historical adjustment can corrupt indicators and comparative statistics.

## 8. Data validation gates

Validation produces `PASS`, `PASS_WITH_WARNINGS`, or `FAIL` and checks:

### Schema and types

- required columns present;
- timestamps timezone-aware;
- finite numeric values;
- symbol/feed/interval consistent.

### OHLC invariants

- prices greater than zero for the initial supported universe;
- `high >= max(open, close)`;
- `low <= min(open, close)`;
- `high >= low`;
- volume and trade count nonnegative.

### Temporal integrity

- sorted by symbol/time;
- unique key;
- duration matches interval;
- no bars from the future;
- no incomplete bars;
- no overlapping bars;
- bars belong to declared session.

### Coverage

- requested start/end compared with actual;
- missing expected bars by session;
- unexpected bars outside calendar;
- long gaps summarized;
- sessions with low completeness flagged.

Default missing-bar policy is `fail_session`: a session below the configured completeness threshold is excluded from research and listed explicitly. No price forward fill is allowed.

### Statistical sanity

- extreme returns and zero-volume sequences flagged, not automatically deleted;
- suspicious constant prices flagged;
- split-like discontinuities cross-checked against action metadata when available.

## 9. Local import provider

CSV/Parquet import is a first-class provider and the upgrade path for paid data. Import config must map source columns to the canonical schema and state timestamp semantics (`bar_start` or `bar_end`), timezone, adjustment mode, feed, and session type.

The importer must reject ambiguous timestamps. It may not infer local timezone from the developer machine.

## 10. Backtest data access

The engine receives a `DataSlice`/iterator from `DataRepository`, not a raw DataFrame owned by a strategy. Strategy context permits only current and past data.

A causal history API should look conceptually like:

```python
ctx.history(symbol="NVDA", bars=20, fields=["close", "volume"], include_current=True)
```

The repository enforces that the returned maximum `bar_end_utc` is not later than the engine clock. A sentinel test must prove that a future row cannot be read.

## 11. No implicit network rule

`edgeback backtest run` fails with a clear message when required canonical data is absent. It does not download automatically. A deliberate `--allow-download` option may be added later, but must default to false and must resolve a new data manifest before simulation.

## 12. Provider-specific cautions

- yfinance is convenient for recent research but documents a limited intraday lookback and personal-use considerations.
- Alpaca Basic provides a free IEX feed rather than consolidated US-market volume; price/volume-sensitive results must disclose that feed.
- Provider limits can change. Capabilities are queried or documented at ingestion time and stored in the manifest.

See `docs/09_FREE_DATA_SOURCES.md` for the verified starting matrix.


---

## Source file: `docs/04_BACKTEST_ENGINE.md`

# 04 — Backtest Engine and Execution Semantics

## 1. Objective

The engine must answer a precise question: **given only information available at each historical event time, what orders would the strategy have requested, which would risk controls accept, and how would the configured execution model have filled them?**

Correct event timing is more important than speed.

## 2. Engine lifecycle

```text
load resolved config
load and validate dataset manifest
load canonical bars
instantiate calendar, portfolio, risk, execution, strategy
run warmup without trading if configured
for each session:
    session_start
    process chronological bar events
    force/session-close liquidation
    session_end
finalize accounting
write immutable artifacts
compute metrics and report
```

Strategy state is new for each independent run. No module-level mutable state is permitted.

## 3. Bar event sequence

For all bars ending at time `T`:

1. The engine clock advances to `T`.
2. Orders submitted before the current bar and eligible during it are evaluated against the bar's open/high/low/close.
3. Fills are applied in deterministic order.
4. Stops/targets attached to positions filled at the bar open become active for the remainder of that same bar.
5. Portfolio and risk state are marked using the completed current bar.
6. Strategy receives the completed bar at `T`.
7. Strategy emits zero or more `OrderIntent` objects.
8. Risk validates/sizes the intents as a batch.
9. Accepted orders receive `eligible_from = next_bar_start` unless explicitly a future-timed order.
10. State and events are appended to the run ledger.

A signal computed from the close of the current bar cannot fill at that same close. The only same-close action is engine-generated forced session liquidation, tagged separately.

## 4. Supported order semantics

### MVP order types

- Market
- Limit
- Stop market
- Bracket entry with stop-loss and take-profit children
- Cancel request

Stop-limit, trailing stop, partial-fill queue modeling, and market-on-open/close strategy orders may be added later behind the order interface.

### Market order

A market order becomes eligible on the next bar. Base fill is next bar open, then adverse spread/slippage and commission are applied.

### Buy limit

- If bar opens at or below limit, base fill is the better of open and limit, therefore open.
- Otherwise, if low touches limit, base fill is limit.
- Adverse slippage may not make a limit fill worse than its limit.

Sell limit behavior is symmetric.

### Buy stop

- If bar opens above stop, base fill is open, modeling a gap through the stop.
- Otherwise, if high touches stop, base fill is stop.
- Adverse slippage applies.

Sell stop behavior is symmetric.

## 5. Bracket orders and intrabar ambiguity

OHLCV bars do not reveal the path inside a bar. When both stop and target are reachable after an entry or for an existing position, use a configured policy:

- `stop_first` — default and conservative;
- `target_first` — optimistic, allowed only for sensitivity analysis;
- `nearest_to_open` — deterministic proxy;
- `reject_ambiguous_bar` — exclude/close the trade with a warning for research diagnostics.

Every run and report must disclose the policy. A strategy may not choose the policy dynamically.

For a long position that gaps below the stop, stop fill base price is the bar open, not the original stop. For a short position, the rule is symmetric.

## 6. Cost model

Final fill price and cash effects are decomposed and recorded:

```text
base execution price
+/- synthetic half-spread
+/- slippage
+ commission/fees
= effective execution
```

Each fill stores the base price, spread cost, slippage cost, commission, effective price, and model IDs/versions.

### Spread

Because free bar data generally lacks bid/ask quotes, MVP supports a fixed basis-point spread. Half of the full spread is applied adversely per side. A symbol/time-dependent model may be added later.

### Slippage

MVP supports:

- fixed basis points;
- optional volume participation impact with a configured cap.

An order exceeding the bar participation cap is rejected or resized according to config. Default is reject with reason `VOLUME_PARTICIPATION_EXCEEDED`; silent full fills are forbidden.

### Commission

Models: zero, fixed/order, per-share with minimum, or basis points. Even when commission is zero, research acceptance must include nonzero spread/slippage stress.

## 7. Portfolio accounting

The portfolio ledger is the only component that changes cash and positions. Fills are immutable double-entry-like events.

Required fields include:

- cash;
- long/short quantity per symbol;
- average price;
- realized and unrealized P&L;
- gross and net exposure;
- equity;
- fees/costs;
- daily/session P&L.

Default MVP rules:

- integer shares;
- maximum leverage 1.0 unless explicitly enabled;
- no negative cash for long purchases unless margin is enabled;
- short proceeds and margin are handled by a documented simplified model;
- all positions are flat at the end of the configured session.

## 8. Risk pipeline

Strategy emits an intent, not a final quantity. Risk rules execute in a stable order:

1. trading-session and entry-time eligibility;
2. direction permission and symbol allowlist;
3. daily lockout/max trades;
4. stop-distance validity;
5. position sizing;
6. per-position limit;
7. gross/net exposure and cash/margin;
8. volume participation;
9. duplicate/conflicting order checks.

Every modification/rejection receives a reason code.

### Risk-per-trade sizing

For an entry with a valid stop:

```text
risk_budget = current_equity * risk_per_trade_pct
risk_per_share = abs(entry_reference - stop_price) + estimated_round_trip_cost_per_share
quantity = floor(risk_budget / risk_per_share)
```

Quantity is then capped by notional, exposure, cash/margin, and participation limits. The actual estimated risk is stored.

## 9. Daily controls

Configurable controls:

- maximum realized plus mark-to-market daily loss;
- maximum trades per session;
- maximum consecutive losses;
- maximum concurrent positions;
- earliest/latest entry time;
- cooldown after exit;
- forced liquidation time/session close.

When daily lockout triggers, pending entries are canceled. Protective exits remain active.

## 10. Session close

Default `force_flat_at_session_end=true`.

The engine generates a special liquidation event for open positions on the final regular-session bar. It uses the final bar close plus adverse slippage and costs, and is tagged `FORCED_SESSION_CLOSE`. Strategy logic cannot inspect that close and then request a same-close fill.

On early-close days, the calendar-provided close governs. No hard-coded 16:00 assumption is allowed.

## 11. Warmup

Strategies declare required warmup bars or sessions. During warmup:

- history/indicators are populated;
- orders are disabled;
- no performance is counted;
- warmup may precede a validation/test window;
- parameters may not be fitted using validation/test outcomes.

A run fails when insufficient warmup exists unless config explicitly allows a shorter warmup with a report warning.

## 12. Deterministic ordering

Order/fill IDs are monotonic within a run. At equal timestamps, sort by:

1. event phase;
2. order priority descending;
3. canonical symbol ascending;
4. creation sequence.

Randomized models require a seeded RNG owned by the run context. No component calls an unseeded global RNG.

## 13. Engine pseudocode

```python
for session in calendar.sessions(range):
    strategy.on_session_start(read_only_context)
    risk.on_session_start(session)

    for timestamp, bars_at_timestamp in clock.iter_session(session):
        fills = broker.evaluate_eligible_orders(bars_at_timestamp)
        portfolio.apply(fills)
        risk.observe_fills(fills)

        portfolio.mark_to_market(bars_at_timestamp)
        intents = strategy_dispatch.on_bars(bars_at_timestamp, causal_context)
        orders = risk.evaluate_and_size(intents, portfolio.snapshot())
        broker.submit(orders, eligible_next_bar=True)
        ledger.append(timestamp, bars_at_timestamp, intents, orders, fills)

    fills = broker.force_flat_at_close(session.final_bar)
    portfolio.apply(fills)
    strategy.on_session_end(read_only_context)
```

The actual implementation may optimize iteration but must preserve this observable sequence.

## 14. Required outputs

- all intents, including rejected ones;
- orders and status transitions;
- fills and cost decomposition;
- closed trades with entry/exit linkage;
- per-event or per-bar equity snapshots;
- daily/session P&L;
- risk events and lockouts;
- warnings for ambiguous bars, data quality, short assumptions, and forced exits.


---

## Source file: `docs/05_STRATEGY_PLUGIN_SPEC.md`

# 05 — Strategy Plugin Specification

## 1. Objective

Strategies are replaceable research modules. A strategy decides **when and why it wants exposure**. It does not download data, calculate fill prices, change cash, bypass risk rules, or write artifacts.

Every strategy lives in one Python file under the trusted top-level `strategies/` package.

## 2. File and identity convention

```text
strategies/<strategy_id>.py
strategy_specs/<strategy_id>.yaml
strategies/__init__.py
```

Rules:

- `strategy_id` is lowercase snake_case and stable.
- Strategy code declares semantic `strategy_version`.
- Config references `strategy.name`, not a file path supplied by an untrusted user.
- Registry imports only the trusted `strategies` package; arbitrary filesystem imports are disabled.
- No ticker symbol may be embedded in strategy logic. Symbol-specific values belong in config.

## 3. Public contract

A typed contract should be equivalent to:

```python
class Strategy(ABC, Generic[ParamsT]):
    strategy_id: ClassVar[str]
    strategy_version: ClassVar[str]
    params_model: ClassVar[type[ParamsT]]

    @classmethod
    def metadata(cls) -> StrategyMetadata: ...

    def initialize(self, ctx: StrategyContext) -> None: ...
    def on_session_start(self, ctx: StrategyContext) -> None: ...
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]: ...
    def on_order_update(self, ctx: StrategyContext, event: OrderEvent) -> None: ...
    def on_session_end(self, ctx: StrategyContext) -> list[OrderIntent]: ...
    def finalize(self, ctx: StrategyContext) -> None: ...
```

`on_bar` receives a bar only after it is complete. In multi-symbol runs it is invoked in deterministic symbol order. A future portfolio strategy may receive `on_timestamp(ctx, bars)` behind a declared `scope=portfolio` contract.

## 4. Strategy metadata

Required metadata:

- strategy ID and version;
- human-readable name and description;
- supported markets/timeframes;
- supported directions;
- scope: `per_symbol` or `portfolio`;
- required fields/features;
- warmup bars/sessions;
- whether previous-session data is required;
- parameter schema;
- research status: `hypothesis`, `experimental`, or `validated_for_dataset`;
- known limitations.

The status `validated_for_dataset` is not a statement of future profitability and must name the dataset/research report.

## 5. Parameter model

Each module defines a strict Pydantic parameter model. Requirements:

- unknown keys rejected;
- ranges and cross-field constraints validated;
- times use explicit exchange-local `HH:MM` values;
- percentages have unambiguous units in names, such as `_pct` or `_bps`;
- defaults are conservative and documented;
- no provider credentials or paths in strategy parameters.

## 6. Read-only causal context

Allowed context capabilities:

- current engine time and session metadata;
- current symbol/bar;
- causal historical bars up to current time;
- read-only position and portfolio snapshot;
- session counters and prior fills/orders for this strategy;
- pure feature helpers;
- intent factory methods;
- structured strategy logging.

Forbidden capabilities:

- future bars or full unmasked DataFrame;
- direct portfolio mutation;
- direct broker/fill calls;
- filesystem/network access;
- environment variables/secrets;
- report/database writes;
- global mutable state.

The context layer must enforce time boundaries rather than trusting strategy authors.

## 7. Intent model

An `OrderIntent` includes:

- strategy ID/version;
- symbol and side;
- intent type: entry, exit, reduce, cancel;
- order type and price fields;
- optional desired quantity or sizing instruction;
- stop price/distance and target price/R-multiple where applicable;
- time-in-force/session expiration;
- priority;
- reason code and concise rationale;
- signal timestamp;
- feature snapshot needed for audit.

Strategies should usually request a sizing method rather than compute final share quantity. The risk manager owns final sizing.

## 8. State rules

Strategy instance state may contain only values necessary for behavior, such as the opening-range high/low or whether a trade was taken this session. State must be serializable to JSON-compatible structures for debugging/checkpoints.

State resets must be explicit. Session state must not accidentally leak into the next day.

## 9. Feature rules

Reusable indicators are pure causal functions under `src/edgeback/features/`. A feature computed at bar `T` may use only bars ending at or before `T`.

- Rolling windows specify minimum periods.
- VWAP resets according to the declared session.
- ATR and prior-close logic define gap/session behavior.
- No centered windows.
- No negative shifts.
- No global normalization using future samples.

Each strategy test includes a future-data mutation test: changing bars after time `T` must not change signals at or before `T`.

## 10. Strategy implementation template

The final repository should provide a compileable template similar to:

```python
@register_strategy
class ExampleStrategy(Strategy[ExampleParams]):
    strategy_id = "example_strategy"
    strategy_version = "0.1.0"
    params_model = ExampleParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            scope="per_symbol",
            warmup_bars=20,
            required_fields=("open", "high", "low", "close", "volume"),
            research_status="hypothesis",
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        history = ctx.history(bar.symbol, bars=20)
        if len(history) < 20:
            return []
        # Causal hypothesis logic only; risk manager determines final size.
        return []
```

## 11. Adding a strategy

1. Add a hypothesis file under `strategy_specs/`.
2. Add one module under `strategies/`.
3. Define strict parameters and metadata.
4. Register the strategy.
5. Add unit tests for entries, exits, warmup, session reset, and no-look-ahead.
6. Add a tiny golden backtest fixture.
7. Verify `edgeback strategies list` and `edgeback strategies describe <id>`.
8. Update `TASK.md` and the strategy research status.

No engine edit should be necessary. If it is, the strategy is depending on missing general capability; add that capability through an interface and record an ADR.

## 12. Seed strategies

The design bundle includes three hypothesis specs:

- `opening_range_breakout`
- `vwap_mean_reversion`
- `gap_momentum`

They are test cases and research starting points, not proven edges. Implement ORB first because it exercises session state, time windows, bracket exits, and next-bar timing without requiring a second data feed.


---

## Source file: `docs/06_EDGE_RESEARCH_PROTOCOL.md`

# 06 — Edge Research Protocol

## 1. Definition of an edge in this project

A candidate edge is a clearly stated, causal market hypothesis that remains economically positive after realistic costs across unseen sessions and reasonable perturbations. A profitable backtest alone is not an edge.

EdgeBack reports evidence and uncertainty. It does not certify profitability.

## 2. Hypothesis card

Every strategy begins with a file under `strategy_specs/` containing:

- economic/behavioral hypothesis;
- target instruments and market regime;
- exact observable inputs available at decision time;
- entry and exit logic;
- risk logic;
- expected holding period and trade frequency;
- falsification criteria;
- major biases/limitations;
- parameter ranges chosen before viewing final test results.

A strategy without a hypothesis card may be used for engine testing but not promoted through the research workflow.

## 3. Research stages

### Stage A — Mechanical validation

- Confirm signals and fills on tiny hand-built bars.
- Prove no future access and next-bar timing.
- Confirm costs, stops, targets, and forced close.
- Visually inspect a small sample of trades.

### Stage B — Baseline

Run a simple predeclared parameter set. Record gross and net results. Do not optimize before the baseline is stored.

### Stage C — Train/validation exploration

Explore a bounded parameter grid or deterministic random sample using training sessions. Use validation sessions for model/parameter selection. Track every trial, including failures.

### Stage D — Final holdout

Run the selected rule once on untouched test sessions. Do not return to tuning based on this result. If the hypothesis changes, create a new strategy version and a new holdout.

### Stage E — Walk-forward

Use rolling or anchored session windows. Fit/select only inside each training window, apply to the next out-of-sample window, and concatenate only OOS trades.

### Stage F — Stress and robustness

- 2x and 3x cost stress;
- entry delayed by one additional bar;
- nearby parameter values;
- symbol subsets;
- year/month/regime slices;
- removal of best day and best trade;
- missing-session sensitivity;
- alternative same-bar ambiguity policy;
- bootstrap confidence intervals.

### Stage G — Paper observation

Outside the MVP engine, monitor prospective signals without capital before considering live use. This stage must not be backfilled into historical validation.

## 4. Data splitting rules

- Split by complete exchange sessions, never random rows.
- Default illustrative split: 60% train, 20% validation, 20% final test.
- For short free-data windows, report that statistical power is limited; do not relax the meaning of holdout.
- Provide warmup data before each evaluation window, but prevent trades and parameter fitting in warmup.
- Use at least a one-session embargo when labels/trades can overlap boundaries.
- Preserve chronological order.

## 5. Selection criteria

Do not optimize a single metric. A candidate should be evaluated on:

- net P&L and return after costs;
- maximum drawdown;
- profit factor;
- expectancy per trade;
- win rate and payoff ratio;
- daily Sharpe/Sortino with sample size shown;
- exposure and turnover;
- trade count and active sessions;
- concentration by day, trade, symbol, and time bucket;
- cost share of gross profit;
- out-of-sample consistency.

The report may provide a ranking score for workflow convenience, but must show its formula and all component metrics.

## 6. Default promotion gates

These defaults are research warnings rather than universal truths. Config may override them, and the report must show overrides.

A strategy version is not promoted beyond `hypothesis` unless:

- no mechanical/look-ahead test fails;
- final test and aggregate walk-forward net expectancy are positive;
- at least 100 OOS trades exist, or the report explicitly states insufficient evidence;
- no single trade contributes more than 20% of OOS net profit;
- no single session contributes more than 30% of OOS net profit;
- results remain nonnegative under 2x baseline transaction costs;
- nearby parameters form a plateau rather than one isolated optimum;
- at least two symbols or two non-overlapping market periods support the effect, when the hypothesis claims generality;
- drawdown and capital requirements fit the declared risk budget.

Failing a gate does not delete the experiment. It changes the conclusion.

## 7. Overfitting controls

- Record the number of tested parameter combinations and strategy versions.
- Never overwrite failed trials.
- Keep the final test immutable.
- Use constrained parameter ranges derived from the hypothesis.
- Prefer simple rules with fewer degrees of freedom.
- Report both best and median validation performance across nearby parameters.
- Add Deflated Sharpe Ratio or Probability of Backtest Overfitting in a later milestone if experiment volume becomes large.

## 8. Bootstrap and uncertainty

Bootstrap at the session level by default to preserve within-day trade dependence. Produce confidence intervals for net expectancy, daily return, profit factor where numerically stable, and max drawdown distributions. Set and record the seed.

A confidence interval crossing zero must be displayed prominently rather than hidden by a point estimate.

## 9. Regime and slice analysis

Without fitting on final test outcomes, report results by:

- symbol;
- long/short;
- weekday;
- entry hour;
- volatility bucket derived causally;
- gap direction/size where relevant;
- trend/range proxy defined before analysis;
- calendar year/month when history permits.

Slice analysis is diagnostic. Post-hoc profitable slices are not a new edge until turned into a versioned hypothesis and retested on new data.

## 10. Experiment record

Each trial stores:

- parent research ID and trial ID;
- hypothesis/strategy version;
- resolved parameters;
- split/fold identity;
- dataset and provider/feed hashes;
- cost and fill policies;
- code/dependency metadata;
- seed;
- metrics and gate outcomes;
- warnings and failure reason;
- artifact paths.

## 11. Required report conclusion labels

Use one of:

- `ENGINE_VALIDATION_ONLY`
- `INSUFFICIENT_EVIDENCE`
- `IN_SAMPLE_ONLY`
- `OOS_FAILED`
- `OOS_PROMISING_NOT_ROBUST`
- `ROBUST_ON_TESTED_DATA`

Never use `PROVEN`, `GUARANTEED`, or equivalent language.

## 12. Seed hypothesis usage

The included ORB, VWAP mean-reversion, and gap-momentum specifications are deliberately ordinary. Their purpose is to exercise the research pipeline and provide falsifiable starting hypotheses. They must not be presented as recommendations to trade.


---

## Source file: `docs/07_CLI_CONFIG_AND_ARTIFACTS.md`

# 07 — CLI, Configuration, and Artifacts

## 1. CLI principles

- Commands are scriptable and return meaningful exit codes.
- Human output is concise; detailed structured logs go to files.
- Backtest commands are offline by default.
- Config can be fully reproduced from the resolved artifact.
- Destructive overwrite is not permitted.

## 2. Proposed command surface

```bash
edgeback --version
edgeback doctor

edgeback strategies list
edgeback strategies describe opening_range_breakout

edgeback data providers
edgeback data download -c configs/example_backtest.yaml
edgeback data import -c configs/local_import.yaml
edgeback data validate -c configs/example_backtest.yaml
edgeback data list

edgeback backtest run -c configs/example_backtest.yaml
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL
edgeback backtest batch -c configs/example_backtest.yaml

edgeback research sweep -c configs/example_sweep.yaml
edgeback research walk-forward -c configs/example_sweep.yaml

edgeback runs list
edgeback runs show <run_id>
edgeback report build <run_id>
```

`doctor` checks Python/dependencies, writable directories, config validity, optional credentials, calendar availability, and whether fixture tests can run. It must not print secret values.

## 3. Configuration precedence

Lowest to highest:

1. application defaults;
2. referenced base YAML;
3. selected YAML;
4. environment variables for secrets only;
5. explicit CLI overrides.

The resolved config must record where each override came from when practical. Unknown keys fail validation.

## 4. Main configuration sections

```yaml
project:        # name, tags, notes, seed
market:         # calendar, timezone, session
data:           # provider/feed, symbols, interval, range, cache, adjustment
engine:         # capital, fill timing, ambiguity, liquidation
execution:      # spread, slippage, commission, participation
risk:           # sizing and limits
strategy:       # strategy ID and strict parameters
report:         # output formats and diagnostics
```

The actual example is `configs/example_backtest.yaml`.

## 5. Symbol overrides

`--symbol` may be repeated. CLI symbols replace `data.symbols` unless a separate `--append-symbol` is introduced. The resolved config records the replacement.

Examples:

```bash
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL --symbol MSFT
```

No strategy file edit is required.

## 6. Parameter overrides

Support typed overrides without evaluating Python:

```bash
edgeback backtest run \
  -c configs/example_backtest.yaml \
  --param opening_range_minutes=30 \
  --param reward_risk=2.0
```

The strategy's Pydantic model parses and validates values. Unknown parameter names fail.

A generic `--set path=value` may be added later using safe typed parsing, but explicit common flags are preferred.

## 7. Date ranges

Exactly one mode:

### Explicit

```yaml
data:
  date_range:
    mode: explicit
    start: "2025-01-01"
    end: "2025-06-30"
```

### Rolling

```yaml
data:
  date_range:
    mode: rolling
    lookback_calendar_days: 55
    end: null
```

Rolling ranges are resolved to exact timestamps before data lookup and persisted. This preserves reproducibility even though the input was relative.

## 8. Run IDs and directory layout

Example:

```text
runs/20260821T071500Z__opening_range_breakout__5m__8f31c2a4/
├── RUN_STATE.json
├── config.input.yaml
├── config.resolved.yaml
├── run_metadata.json
├── data_manifest.json
├── warnings.json
├── logs.jsonl
├── intents.parquet
├── orders.parquet
├── fills.parquet
├── trades.parquet
├── equity.parquet
├── daily_returns.parquet
├── metrics.json
├── gate_results.json
└── report.html
```

Required `RUN_STATE` transitions: `CREATED`, `RUNNING`, `COMPLETED` or `FAILED`. Completed directories are immutable.

## 9. Run metadata

See `schemas/run_metadata.schema.json`. Include:

- run/research/trial IDs;
- timestamps and duration;
- status;
- strategy identity;
- config/data hashes;
- code commit and dirty flag;
- Python/package versions;
- host platform summary without sensitive identifiers;
- seed;
- execution-model IDs;
- parent/fold links;
- artifact checksums;
- warnings and conclusion label.

## 10. Metrics artifact

`metrics.json` must state units and denominator assumptions. At minimum:

- starting/ending equity;
- gross/net P&L and return;
- total costs and cost/gross-profit ratio;
- max drawdown amount and percent;
- daily Sharpe and Sortino with observation count;
- trade count, active sessions, trades/session;
- win rate, average win/loss, payoff, expectancy, profit factor;
- average/median holding time;
- long/short and per-symbol summaries;
- exposure and turnover;
- forced exits and ambiguous bars;
- data completeness and excluded sessions.

Undefined metrics are `null` with a reason, not `NaN` serialized unpredictably.

## 11. HTML report sections

1. Identity and reproducibility
2. Data/provider/feed limitations
3. Strategy and parameters
4. Execution/risk assumptions
5. Summary and conclusion label
6. Equity and drawdown
7. Daily/session returns
8. Trade distributions and MAE/MFE where available
9. Breakdown by symbol, side, weekday, and entry time
10. Cost waterfall and stress comparison
11. OOS/fold/parameter robustness when applicable
12. Warnings, excluded data, and research gates

## 12. Exit codes

Suggested stable codes:

- `0` success
- `2` configuration error
- `3` data unavailable
- `4` data validation failed
- `5` strategy loading/parameter error
- `6` simulation failed
- `7` artifact/report write failed
- `8` research gate failed when `--fail-on-gate` is requested

A non-promising strategy is normally a successful computation (`0`) with an appropriate conclusion label, not an application crash.

## 13. Logging

Console: progress and final artifact path.

JSONL log: timestamp UTC, level, component, run ID, event/reason code, symbol where applicable, and redacted context. Never log API secrets or complete environment dumps.

## 14. Configuration migration

Every config has `config_version`. Loaders may migrate old versions explicitly and record the migration. Unknown future versions fail with guidance. Silent reinterpretation is forbidden.


---

## Source file: `docs/08_TESTING_AND_ACCEPTANCE.md`

# 08 — Testing and Acceptance

## 1. Testing philosophy

The most dangerous bugs in a backtester produce plausible profits. Tests must focus on timing, accounting, data boundaries, ambiguity, and reproducibility before visual reports or speed.

Core tests use tiny local fixtures and no network.

## 2. Test layers

### Unit tests

- config parsing/validation/overrides;
- symbol normalization and provider mapping;
- bar schema and validation rules;
- exchange session/early close boundaries;
- feature functions;
- each order-type fill rule;
- spread/slippage/commission decomposition;
- risk sizing and limits;
- portfolio accounting;
- metrics formulas;
- strategy state transitions.

### Contract tests

Run the same cases against every implementation of:

- market data provider normalization;
- calendar;
- commission/spread/slippage model;
- position sizer;
- strategy plugin;
- artifact registry.

### Integration tests

- fixture canonical data -> engine -> artifacts -> report;
- config/CLI override -> resolved config;
- multi-symbol deterministic ordering;
- failure run preserves logs/state;
- completed run cannot be overwritten.

### Optional network tests

Marked `network` and skipped by default. Verify provider adapters with tiny requests. Never rely on them for core CI.

### Golden tests

Use hand-built bars with exact expected intents, fills, costs, positions, and final metrics. Store expected outputs in readable JSON/CSV. Changes require explicit review, not blind snapshot update.

## 3. Mandatory timing tests

1. **No same-bar fill:** signal from bar close at `T` fills no earlier than next bar open.
2. **Future mutation:** changing bars after `T` does not change signals/orders at or before `T`.
3. **Warmup isolation:** warmup creates no trades.
4. **Gap through stop:** fill occurs at adverse open plus costs.
5. **Both stop and target touched:** configured ambiguity policy is honored.
6. **Entry and bracket same bar:** bracket activation and ambiguity are deterministic.
7. **Early close:** forced liquidation uses calendar close.
8. **Missing next bar:** pending market order follows configured expiry; it is not backfilled.

## 4. Accounting invariants

Property/invariant tests should assert:

- cash changes only through fills/fees/corporate actions;
- position quantity equals cumulative signed fills;
- realized P&L reconciles with closed lots/trades;
- equity equals cash plus marked position value under the chosen short accounting model;
- all fills reference an existing accepted order;
- fill time is not before order eligibility;
- flat-at-close holds when enabled;
- no order exceeds configured risk/exposure after resizing;
- deterministic reruns produce identical canonical outputs.

## 5. Data tests

- duplicate keys fail;
- timezone-naive timestamps fail;
- invalid OHLC fails;
- incomplete current bar is excluded/fails according to policy;
- resampling never crosses sessions;
- missing bars are reported, not forward-filled;
- mixed provider/feed/adjustment fails;
- dataset hash changes when canonical content changes.

## 6. Strategy tests

Every strategy requires:

- parameter validation;
- warmup behavior;
- expected entry and non-entry cases;
- expected exits;
- session reset;
- no hard-coded symbol behavior by running the same fixture under two symbols;
- no-look-ahead future mutation test;
- one tiny golden end-to-end run.

## 7. Metrics tests

Use manually calculable trade and daily-return fixtures. Test zero trades, all wins, all losses, zero variance, no drawdown, undefined profit factor, and negative equity guardrails. Serialize undefined values as `null` plus reason.

## 8. Artifact tests

- temp directory becomes completed atomically;
- failure state persists diagnostics;
- required files exist and validate against schemas;
- artifact checksums match;
- secrets and `.env` values are absent;
- completed run is immutable;
- HTML generation does not mutate metrics.

## 9. Quality gates

Milestone completion requires:

```bash
pytest
ruff check .
ruff format --check .
```

Static type checking must pass once configured. Recommended coverage targets:

- engine/execution/risk/accounting: at least 90%;
- overall package: at least 80%.

Coverage does not replace behavioral tests.

## 10. MVP acceptance scenario

A clean checkout with fixture data must:

1. install from `pyproject.toml`;
2. run `edgeback doctor` successfully;
3. list and describe ORB;
4. validate a two-symbol 5m fixture dataset;
5. run ORB with next-bar fills, costs, stop/target, and forced close;
6. create all required run artifacts;
7. rerun identically and match trades/metrics hashes;
8. change symbol through CLI without editing code;
9. reject a deliberately invalid/mixed dataset;
10. pass all offline tests and quality gates.

## 11. Research acceptance scenario

Using a sufficiently long canonical dataset when available:

1. run a bounded sweep;
2. persist every trial;
3. select on train/validation only;
4. execute a chronological final test;
5. execute walk-forward folds;
6. run 2x/3x cost and parameter-neighborhood stress;
7. produce a conclusion label and gate results;
8. preserve the untouched final-test identity.

## 12. Performance benchmarking

Add non-CI benchmarks for event throughput, memory, artifact size, and report time. Optimization may not change golden outputs. Any vectorized optimization must pass the same no-look-ahead and fill-semantics tests as the reference implementation.


---

## Source file: `docs/09_FREE_DATA_SOURCES.md`

# 09 — Free Intraday Data Sources and Upgrade Path

Verified for design purposes on **2026-08-21**. Provider plans and limits can change; the implementation must re-check capabilities and store a capability snapshot in each data manifest.

## 1. Starting matrix

| Provider | Cost/start requirement | Useful scope | Important limitation | EdgeBack role |
|---|---|---|---|---|
| yfinance / Yahoo public endpoints | No key; Python package | Recent 1m/2m/5m/15m/etc. stock bars | yfinance documents that intraday history cannot extend beyond the latest 60 days; it is unofficial and intended for research/personal use subject to Yahoo terms | Default smoke-test/recent-data adapter |
| Alpaca Market Data Basic, IEX feed | Free account and API keys | US stock/ETF historical data since 2016 according to Alpaca plan docs | Free equity feed is IEX rather than consolidated SIP; the Basic plan documents a latest-15-minute historical-data restriction and 200 historical API calls/minute. Alpaca describes IEX as a small fraction of total US market volume, so volume and some price behavior differ from whole-market data | Optional longer-history adapter; disclose `feed=iex` prominently |
| Local CSV/Parquet | Depends on user-supplied source | Any data that can be mapped to canonical schema | Quality, licensing, timestamp semantics, adjustments, and survivorship depend on the source | First-class import and future paid-data upgrade path |
| Alpha Vantage | API key; plan-dependent | Intraday endpoint exists | Current official documentation marks `TIME_SERIES_INTRADAY` as Premium; do not assume it is a free MVP source | Optional future adapter only after plan verification |

## 2. Recommended MVP sequence

### Step 1 — Local fixtures

Implement and validate the entire engine using hand-built fixture data. This prevents provider quirks from hiding engine bugs.

### Step 2 — yfinance

Use for installation smoke tests and recent 5m research. Request explicit parameters; never rely on library defaults for adjustment or extended hours. Cache immediately and record the package version, request, source, and limitation warning.

### Step 3 — Alpaca IEX

Add for longer historical experiments. Require `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` through environment variables. Record `source_feed=iex`. Do not compare IEX volume-sensitive results directly with consolidated/Yahoo results as though they were the same dataset.

### Step 4 — Local paid/consolidated import

When research justifies spending, import a higher-quality dataset through the canonical CSV/Parquet adapter. Engine and strategy code remain unchanged.

## 3. Provider-selection policy

- Provider/feed is explicit in config.
- No fallback from one provider to another.
- No stitching providers into one symbol history by default.
- Dataset and report names include provider/feed.
- Research comparisons use the same provider/feed or clearly separate the result.
- Rate limits and latest-bar delays are stored in capability metadata.

## 4. What free OHLCV cannot model well

- true bid/ask spread and queue position;
- consolidated volume when using a single-exchange feed;
- market impact for larger orders;
- halts and detailed auction behavior;
- borrow availability and short locate fees;
- exact order path inside each bar;
- point-in-time universe membership and delisted symbols;
- corporate-action-perfect history.

The report must state these limitations. Synthetic cost stress is mandatory but cannot fully replace quote/tick data.

## 5. Data-quality comparison procedure

Before changing the primary provider:

1. Download overlapping sessions for a liquid symbol.
2. Compare bar counts, open/high/low/close differences, volume ratios, missing bars, split handling, and session boundaries.
3. Run the same fixed strategy/config against each provider as separate datasets.
4. Attribute differences to data source rather than treating them as strategy improvements.
5. Record the decision in `DECISIONS.md`.

## 6. Official references

- yfinance download reference: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- yfinance legal/project disclaimer: https://ranaroussi.github.io/yfinance/
- Alpaca market-data plan overview: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca historical stock feed description: https://docs.alpaca.markets/us/docs/historical-stock-data-1
- Alpha Vantage API documentation: https://www.alphavantage.co/documentation/

These references are implementation inputs, not permanent guarantees. Re-verify before coding provider-specific assumptions.


---

## Source file: `strategy_specs/README.md`

# Strategy Specification Files

Each YAML file is a falsifiable hypothesis and implementation contract. It is not executable code and does not claim an edge.

One strategy should map to:

```text
strategy_specs/<id>.yaml
strategies/<id>.py
tests/strategies/test_<id>.py
```

Required fields:

- `id`, `version`, `research_status`
- target market/timeframes/directions
- hypothesis and falsification criteria
- required causal data
- session state and warmup
- strict parameters with units/ranges
- entry and exit rules
- risk intent fields
- invariants and acceptance tests
- known biases/limitations

When rules change in a way that can alter signals, increment the strategy version. Preserve old experiment identity. A post-hoc filter discovered from final-test results requires a new version and new unseen data.


---

## Source file: `strategy_specs/opening_range_breakout.yaml`

spec_version: "1.0"
id: "opening_range_breakout"
version: "0.1.0"
research_status: "hypothesis"
name: "Opening Range Breakout"

scope:
  markets: ["US_EQUITY", "US_ETF"]
  timeframes: ["1m", "5m", "15m"]
  directions: ["long", "short"]
  session: "regular"

hypothesis: >-
  The first minutes of the regular session reveal an initial price-discovery
  range. A close beyond that range, when accompanied by stronger-than-recent
  intraday volume and a non-extreme range width, may continue before the close.

falsification:
  - "Out-of-sample expectancy is not positive after baseline costs."
  - "Performance disappears under a one-bar additional entry delay."
  - "Profit is dominated by one trade/session or an isolated parameter value."

required_data:
  fields: ["open", "high", "low", "close", "volume"]
  previous_sessions: 1
  warmup_bars: 20
  extended_hours_required: false

session_state:
  - "opening_range_high"
  - "opening_range_low"
  - "opening_range_complete"
  - "trades_taken_by_direction"
  - "pending_breakout"

parameters:
  opening_range_minutes:
    type: "int"
    default: 15
    minimum: 5
    maximum: 60
  directions:
    type: "enum"
    values: ["long", "short", "both"]
    default: "both"
  breakout_buffer_bps:
    type: "float"
    default: 5.0
    minimum: 0.0
    maximum: 50.0
  minimum_opening_range_pct:
    type: "float"
    default: 0.20
    minimum: 0.0
    maximum: 5.0
  maximum_opening_range_pct:
    type: "float"
    default: 2.50
    minimum: 0.1
    maximum: 20.0
  volume_ratio_lookback_bars:
    type: "int"
    default: 20
    minimum: 5
    maximum: 100
  minimum_volume_ratio:
    type: "float"
    default: 1.20
    minimum: 0.0
    maximum: 10.0
  atr_period:
    type: "int"
    default: 14
    minimum: 2
    maximum: 100
  stop_model:
    type: "enum"
    values: ["opposite_range", "atr", "opposite_range_or_atr"]
    default: "opposite_range_or_atr"
  stop_atr_multiple:
    type: "float"
    default: 0.80
    minimum: 0.1
    maximum: 5.0
  reward_risk:
    type: "float"
    default: 1.50
    minimum: 0.25
    maximum: 10.0
  max_trades_per_symbol_session:
    type: "int"
    default: 1
    minimum: 1
    maximum: 10
  close_if_not_triggered_by:
    type: "local_time"
    default: "14:30"

rules:
  opening_range:
    - "Build high/low from complete bars whose interval lies inside the first opening_range_minutes of regular session."
    - "Do not trade until the opening range is complete."
    - "Reject the session when the opening range width is outside configured percentage bounds."
  long_entry:
    - "Current completed bar close exceeds opening_range_high plus breakout_buffer_bps."
    - "Current bar volume divided by the causal median of the prior lookback bars is at least minimum_volume_ratio."
    - "No long trade has been taken beyond the per-session limit."
    - "Signal time is not later than close_if_not_triggered_by."
    - "Emit a market-entry intent eligible next bar; do not fill on signal close."
  short_entry:
    - "Symmetric close below opening_range_low minus buffer and volume condition."
  stop:
    - "Compute the configured stop reference from the opposite side of the range and/or ATR."
    - "Stop must be on the adverse side of the entry reference and have positive distance."
  target:
    - "Target distance equals reward_risk times initial stop distance."
  exit:
    - "Protective bracket remains active until exit or forced session close."
    - "No overnight position."

intent_requirements:
  sizing: "risk_per_trade"
  include_feature_snapshot:
    - "opening_range_high"
    - "opening_range_low"
    - "opening_range_width_pct"
    - "volume_ratio"
    - "atr"
    - "breakout_level"
    - "stop_reference"

invariants:
  - "No signal before opening range completion."
  - "No hard-coded symbol."
  - "No more than configured trades per symbol/session."
  - "No entry signal after cutoff."
  - "Future bars cannot change prior signals."
  - "Session state resets on every new exchange session."

acceptance_tests:
  - "Long breakout creates one next-bar market intent and a valid bracket."
  - "Short breakout is symmetric."
  - "Low volume prevents entry."
  - "Extreme opening range prevents entry."
  - "Signal exactly at/after cutoff follows the documented boundary rule."
  - "Same fixture works under two different symbols."
  - "A future-bar mutation does not change earlier intents."

known_limitations:
  - "OHLCV cannot reveal breakout path inside the signal bar."
  - "Synthetic spread/slippage replaces quote data."
  - "Opening auction effects are not modeled."
  - "Free-provider volume may not be consolidated."


---

## Source file: `strategy_specs/vwap_mean_reversion.yaml`

spec_version: "1.0"
id: "vwap_mean_reversion"
version: "0.1.0"
research_status: "hypothesis"
name: "Session VWAP Mean Reversion"

scope:
  markets: ["US_EQUITY", "US_ETF"]
  timeframes: ["1m", "5m"]
  directions: ["long", "short"]
  session: "regular"

hypothesis: >-
  After initial price discovery, a liquid instrument that moves unusually far
  from session VWAP without a strong directional regime may revert toward VWAP
  before the close.

falsification:
  - "Out-of-sample mean-reversion trades remain negative after costs."
  - "Results require an isolated deviation threshold."
  - "Losses concentrate on trend days and the predeclared trend filter does not control them."

required_data:
  fields: ["high", "low", "close", "volume"]
  previous_sessions: 1
  warmup_bars: 30
  extended_hours_required: false

parameters:
  earliest_entry_time: {type: "local_time", default: "10:00"}
  latest_entry_time: {type: "local_time", default: "15:00"}
  deviation_atr_multiple: {type: "float", default: 1.25, minimum: 0.25, maximum: 5.0}
  atr_period: {type: "int", default: 14, minimum: 2, maximum: 100}
  maximum_vwap_slope_bps_per_bar: {type: "float", default: 8.0, minimum: 0.0, maximum: 100.0}
  stop_atr_multiple: {type: "float", default: 1.0, minimum: 0.1, maximum: 5.0}
  target: {type: "enum", values: ["vwap", "partial_vwap"], default: "vwap"}
  max_trades_per_symbol_session: {type: "int", default: 2, minimum: 1, maximum: 10}

rules:
  - "Compute session VWAP causally and reset at regular-session open."
  - "Do not enter during the opening exclusion window or after latest entry."
  - "Long when close is sufficiently below VWAP and absolute causal VWAP slope is below the maximum."
  - "Short symmetrically above VWAP."
  - "Target VWAP or configured fraction toward VWAP."
  - "Stop uses ATR beyond the entry reference."
  - "Emit next-bar orders and close by session end."

invariants:
  - "VWAP uses only current and prior regular-session bars."
  - "No hard-coded symbol."
  - "No entry outside time window."
  - "No future normalization."

known_limitations:
  - "Trend-regime proxy is simple and may not generalize."
  - "Provider volume coverage materially affects VWAP."
  - "Quote spread widens during volatile moves but is synthetic in MVP."


---

## Source file: `strategy_specs/gap_momentum.yaml`

spec_version: "1.0"
id: "gap_momentum"
version: "0.1.0"
research_status: "hypothesis"
name: "Gap Direction Momentum"

scope:
  markets: ["US_EQUITY", "US_ETF"]
  timeframes: ["1m", "5m", "15m"]
  directions: ["long", "short"]
  session: "regular"

hypothesis: >-
  A sufficiently large opening gap followed by early confirmation in the same
  direction may continue intraday because overnight information is incorporated
  progressively rather than instantly.

falsification:
  - "Continuation expectancy is not positive out of sample after costs."
  - "Performance is explained only by a few extreme news sessions."
  - "The effect disappears after delaying entry by one bar."

required_data:
  fields: ["open", "high", "low", "close", "volume"]
  previous_sessions: 2
  warmup_bars: 20
  derived: ["previous_regular_session_close"]

parameters:
  minimum_gap_pct: {type: "float", default: 1.0, minimum: 0.1, maximum: 20.0}
  maximum_gap_pct: {type: "float", default: 8.0, minimum: 0.5, maximum: 50.0}
  confirmation_minutes: {type: "int", default: 15, minimum: 5, maximum: 60}
  confirmation_breakout_buffer_bps: {type: "float", default: 5.0, minimum: 0.0, maximum: 100.0}
  minimum_volume_ratio: {type: "float", default: 1.2, minimum: 0.0, maximum: 10.0}
  stop_atr_multiple: {type: "float", default: 1.0, minimum: 0.1, maximum: 5.0}
  reward_risk: {type: "float", default: 1.5, minimum: 0.25, maximum: 10.0}
  latest_entry_time: {type: "local_time", default: "11:30"}

rules:
  - "Gap is regular-session open versus previous regular-session close."
  - "Reject gaps outside configured bounds."
  - "Build an early confirmation range."
  - "For a gap up, enter long only after a completed-bar close confirms above the range plus buffer and volume filter."
  - "For a gap down, use symmetric short confirmation."
  - "Use ATR stop, reward/risk target, next-bar execution, and forced close."

invariants:
  - "Previous close is known before current session opens."
  - "No use of post-close/future information."
  - "No hard-coded symbol."

known_limitations:
  - "No news classification; extreme-event concentration must be reported."
  - "Free data may omit delisted historical gap candidates, creating survivorship bias."
  - "Short borrow availability is unknown."


---

## Source file: `configs/example_backtest.yaml`

config_version: "1.0"

project:
  name: "orb_recent_research"
  tags: ["intraday", "hypothesis", "free-data"]
  notes: "Example only; not a trading recommendation."
  random_seed: 42

market:
  calendar: "XNYS"
  timezone: "America/New_York"
  session: "regular"
  include_extended_hours: false

# Provider is explicit. A backtest uses already-downloaded canonical data.
data:
  provider: "yfinance"
  feed: "yahoo"
  symbols: ["NVDA"]
  interval: "5m"
  date_range:
    mode: "rolling"
    lookback_calendar_days: 55
    end: null
  adjustment_mode: "split_adjusted"
  cache_dir: "data"
  minimum_session_completeness_pct: 98.0
  missing_session_policy: "fail_session"
  allow_incomplete_latest_bar: false

engine:
  initial_cash_usd: 100000.0
  signal_time: "bar_close"
  market_fill_timing: "next_bar_open"
  same_bar_bracket_policy: "stop_first"
  force_flat_at_session_end: true
  entry_allocation: "priority_then_symbol"
  fractional_shares: false
  max_leverage: 1.0

execution:
  spread:
    model: "fixed_bps"
    full_spread_bps: 2.0
  slippage:
    model: "fixed_bps"
    bps_per_side: 1.0
  commission:
    model: "per_share"
    usd_per_share: 0.005
    minimum_usd_per_order: 0.0
  volume_participation:
    max_pct_of_bar_volume: 1.0
    on_exceed: "reject"

risk:
  direction: "both"
  sizing:
    model: "risk_per_trade"
    risk_per_trade_pct_of_equity: 0.25
  max_position_pct_of_equity: 25.0
  max_gross_exposure_pct: 100.0
  max_concurrent_positions: 3
  max_trades_per_session: 4
  max_daily_loss_pct_of_starting_equity: 1.0
  max_consecutive_losses: 3
  entry_start_time: "09:45"
  latest_entry_time: "14:30"
  cooldown_bars_after_exit: 1

strategy:
  name: "opening_range_breakout"
  expected_version: "0.1.0"
  params:
    opening_range_minutes: 15
    directions: "both"
    breakout_buffer_bps: 5.0
    minimum_opening_range_pct: 0.20
    maximum_opening_range_pct: 2.50
    volume_ratio_lookback_bars: 20
    minimum_volume_ratio: 1.20
    stop_model: "opposite_range_or_atr"
    atr_period: 14
    stop_atr_multiple: 0.80
    reward_risk: 1.50
    max_trades_per_symbol_session: 1
    close_if_not_triggered_by: "14:30"

report:
  output_dir: "runs"
  html: true
  write_csv_copies: false
  include_trade_feature_snapshots: true
  include_mae_mfe: true
  bootstrap_samples: 1000
  conclusion_gates_enabled: true


---

## Source file: `configs/example_sweep.yaml`

config_version: "1.0"

research:
  name: "orb_parameter_stability"
  base_config: "configs/example_backtest.yaml"
  random_seed: 42
  mode: "grid"
  max_trials: 200
  split:
    method: "chronological_sessions"
    train_pct: 60.0
    validation_pct: 20.0
    test_pct: 20.0
    embargo_sessions: 1
    final_test_immutable: true
  selection:
    primary_metric: "validation_expectancy_usd_per_trade"
    tie_breakers:
      - "validation_max_drawdown_pct"
      - "validation_profit_factor"
    constraints:
      minimum_validation_trades: 30
      maximum_validation_drawdown_pct: 10.0
      minimum_validation_profit_factor: 1.0
  parameter_grid:
    opening_range_minutes: [10, 15, 30]
    breakout_buffer_bps: [0.0, 5.0, 10.0]
    minimum_volume_ratio: [1.0, 1.2, 1.5]
    stop_atr_multiple: [0.6, 0.8, 1.0]
    reward_risk: [1.0, 1.5, 2.0]
  walk_forward:
    enabled: true
    method: "rolling"
    train_sessions: 120
    validation_sessions: 20
    test_sessions: 20
    step_sessions: 20
  stress:
    cost_multipliers: [1.0, 2.0, 3.0]
    additional_entry_delay_bars: [0, 1]
    remove_best_trade: true
    remove_best_session: true
    parameter_neighborhood: true
    bootstrap_sessions: 2000
  gates:
    minimum_oos_trades: 100
    maximum_single_trade_profit_contribution_pct: 20.0
    maximum_single_session_profit_contribution_pct: 30.0
    require_nonnegative_at_2x_cost: true
    require_parameter_plateau: true


---

## Source file: `TASK.md`

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
| M1 | Configuration and domain models | TODO |
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
| T000 | M0 | TODO | — | Create Python project skeleton and preserve design docs |
| T010 | M0 | TODO | T000 | Configure pytest, Ruff, type checking, and offline CI baseline |
| T020 | M0 | TODO | T000 | Add logging, error hierarchy, `.env.example`, and ignore rules |
| T100 | M1 | TODO | T010 | Implement strict Pydantic configuration models |
| T110 | M1 | TODO | T100 | Implement YAML loader, precedence, and CLI-safe overrides |
| T120 | M1 | TODO | T100 | Implement canonical domain models/enums and serialization |
| T130 | M1 | TODO | T110,T120 | Implement config hashing and reproducibility metadata capture |
| T200 | M2 | TODO | T120 | Implement trading calendar interface and XNYS adapter |
| T210 | M2 | TODO | T120 | Implement canonical bar schema and validation report models |
| T220 | M2 | TODO | T210 | Implement local CSV/Parquet provider and normalization |
| T230 | M2 | TODO | T200,T210 | Implement Parquet repository, partitions, and dataset manifests |
| T240 | M2 | TODO | T230 | Build deterministic fixture datasets and validation/golden inputs |
| T300 | M3 | TODO | T120,T240 | Implement strategy base, context, intents, and trusted registry |
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

**Status:** TODO  
**Deliverables:** `pyproject.toml`, `src/edgeback/`, `tests/`, `strategies/`, package/CLI placeholders, design files retained at root.  
**Acceptance:** package imports; no design file is lost; no generated data committed.  
**Evidence:** _not yet run_

### T010 — Quality baseline

**Status:** TODO  
**Acceptance:** `pytest`, `ruff check .`, `ruff format --check .`, and chosen static type checker run on the skeleton; core tests require no network.  
**Evidence:** _not yet run_

### T020 — Operational baseline

**Status:** TODO  
**Acceptance:** structured logging utility, typed application errors, `.env.example`, and ignore rules cover `.env`, `data/`, `runs/`, caches, virtual environments, SQLite runtime files, and provider payloads. Secrets redaction test exists.  
**Evidence:** _not yet run_

### T100 — Configuration models

**Status:** TODO  
**Acceptance:** models cover all sections in `configs/example_backtest.yaml`; unknown keys fail; cross-field date/risk/order constraints tested; config objects are frozen after resolution.  
**Evidence:** _not yet run_

### T110 — Loader and overrides

**Status:** TODO  
**Acceptance:** documented precedence works; `--symbol` replacement and typed `--param` overrides tested; unsafe YAML tags rejected.  
**Evidence:** _not yet run_

### T120 — Domain models

**Status:** TODO  
**Acceptance:** typed Bar, Intent, Order, Fill, Position, events, reason codes, and statuses serialize deterministically; invalid states rejected.  
**Evidence:** _not yet run_

### T130 — Reproducibility metadata

**Status:** TODO  
**Acceptance:** stable canonical config hash; Git/dependency/seed metadata captured without exposing sensitive host data; dirty tree noted.  
**Evidence:** _not yet run_

### T200 — Calendar

**Status:** TODO  
**Acceptance:** normal day, holiday, daylight-saving period, and early-close fixtures; no fixed UTC-offset logic.  
**Evidence:** _not yet run_

### T210 — Bar schema and validation models

**Status:** TODO  
**Acceptance:** matches `schemas/bar.schema.json`; timezone-naive, duplicate, invalid OHLC, incomplete, mixed-feed cases tested.  
**Evidence:** _not yet run_

### T220 — Local provider

**Status:** TODO  
**Acceptance:** imports mapped CSV and Parquet with explicit timestamp semantics/timezone; ambiguous input fails; provider contract tests pass.  
**Evidence:** _not yet run_

### T230 — Repository and manifests

**Status:** TODO  
**Acceptance:** atomic Parquet partitions, deterministic dataset hash, manifest/validation files, no silent provider mixing.  
**Evidence:** _not yet run_

### T240 — Fixtures

**Status:** TODO  
**Acceptance:** tiny single/multi-symbol sessions include normal fills, gaps, ambiguous brackets, missing bars, and early close; expected outputs are human-readable.  
**Evidence:** _not yet run_

### T300 — Strategy contract and registry

**Status:** TODO  
**Acceptance:** trusted registry, strict parameter models, lifecycle hooks, read-only context, serializable state, and contract tests.  
**Evidence:** _not yet run_

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


---

## Source file: `STATUS.md`

# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-21 (Asia/Singapore)  
**Project state:** DESIGN_COMPLETE_IMPLEMENTATION_NOT_STARTED  
**Current milestone:** M0 — Bootstrap and quality baseline  
**Current task:** T000 — Create Python project skeleton  
**Current task status:** TODO  
**Working tree:** Design bundle only; implementation repository has not been initialized

## Current objective

Create the initial Python 3.12 `src/` project skeleton without deleting or relocating the authoritative design files. Establish package imports, test directories, top-level trusted `strategies/`, and placeholders needed for the next quality task.

## Completed in the latest design session

- Defined product requirements, architecture, data model, engine semantics, strategy contract, edge-research protocol, CLI/artifacts, testing, and free-data policy.
- Created structured ORB, VWAP mean-reversion, and gap-momentum hypothesis specs.
- Created durable task, status, and architecture-decision files.
- Created example backtest/sweep configuration and JSON schemas.

## Implementation completed

None.

## Files expected to be created next

- `pyproject.toml`
- `src/edgeback/__init__.py`
- `src/edgeback/cli.py`
- package directory placeholders matching `docs/02_ARCHITECTURE.md`
- `strategies/__init__.py`
- `tests/test_import.py`
- `.gitignore`
- optional `README` implementation section, without changing design intent

## Validation performed

Design-bundle validation only:

- YAML/JSON syntax validation must be run after extraction.
- No Python implementation tests exist yet.

## Known blockers

None for T000. Internet access and provider API keys are not required until optional provider smoke tests.

## Exact next actions

1. Read `PROJECT_MANIFEST.yaml` and `AGENTS.md`.
2. Change T000 to `IN_PROGRESS` in `TASK.md` and update this status timestamp.
3. Initialize `pyproject.toml` targeting Python 3.12 with an importable `src/edgeback` package.
4. Create the directory skeleton from `docs/02_ARCHITECTURE.md` without implementing business logic prematurely.
5. Add a minimal offline import test.
6. Run the import test, record the command/result under T000, then mark T000 `DONE` only if acceptance is met.
7. Set T010 as the next task and checkpoint this file.

## Resume note

The repository is safe to resume. There are no partial implementation files. Do not skip T000 or start provider integration first.

## Session log

| Date | Agent/session | Task | Outcome |
|---|---|---|---|
| 2026-08-21 | System design | Design package | Specifications and initial state files created; implementation not started |


---

## Source file: `DECISIONS.md`

# DECISIONS.md — Architecture Decision Records

Architecture decisions are append-only. Supersede an ADR with a new ADR rather than deleting history.

## ADR-001 — Build a small custom event-driven engine

**Status:** Accepted  
**Date:** 2026-08-21

**Context:** Intraday correctness depends on precise signal/fill timing, same-bar stop/target ambiguity, cost decomposition, and causal access. Generic frameworks can obscure these rules and make AI-generated integration harder to audit.

**Decision:** Implement a focused event-driven bar engine with typed interfaces. pandas remains the data/analysis layer, not the execution semantics.

**Alternatives:** Backtrader, vectorbt, backtesting.py, fully vectorized custom code.

**Consequences:** More initial code and tests, but semantics are explicit. Performance optimization must preserve golden outputs.

## ADR-002 — Configuration controls symbols and parameters

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** No core or strategy code contains a required ticker literal. YAML and CLI overrides select symbols. Provider-specific mappings are isolated in data adapters.

**Consequences:** Strategies remain portable; configs and manifests become critical reproducibility artifacts.

## ADR-003 — One strategy per trusted Python file

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** User strategies live under top-level `strategies/`, are registered by stable ID/version, and use strict parameter models. Arbitrary path imports and code generation from YAML are forbidden.

**Consequences:** Adding strategies is simple and auditable while avoiding an unsafe plugin loader.

## ADR-004 — Separate ingestion from simulation

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** Data download/import creates canonical Parquet plus a manifest. Backtests are offline by default and reference immutable dataset IDs.

**Consequences:** Reproducibility improves; users perform an explicit acquisition step.

## ADR-005 — Free-data baseline is yfinance plus optional Alpaca IEX

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** yfinance is the default recent-data adapter; Alpaca Basic/IEX is optional for longer history. Local CSV/Parquet is first-class. No silent fallback or provider stitching.

**Consequences:** MVP is affordable, but reports must disclose limited lookback, terms, feed coverage, and data quality. Volume-sensitive findings on IEX require caution.

## ADR-006 — Canonical bars have start and end timestamps

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** Store `bar_start_utc` and `bar_end_utc`. A completed bar is delivered at its end time. This removes provider timestamp ambiguity from engine behavior.

**Consequences:** Provider adapters must explicitly map timestamp semantics; resampling and tests are clearer.

## ADR-007 — Signals fill no earlier than the next bar

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** A signal based on a completed bar cannot fill on that bar. Default market fill is next bar open. Engine-generated forced session liquidation is the only final-close exception and is tagged.

**Consequences:** Results are more conservative and causal. Strategies that need intrabar decisions require finer input bars or a future event type.

## ADR-008 — Conservative same-bar bracket policy

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** When stop and target are both touched and path is unknown, default to `stop_first`. Alternative policies are sensitivity settings disclosed in reports.

**Consequences:** Avoids optimistic bias but may understate some fills. Tick/quote data would be needed to resolve path accurately.

## ADR-009 — pandas + Parquet + SQLite for MVP

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** pandas handles tabular transforms, Parquet stores canonical bars/results, and SQLite indexes runs/experiments. Per-run files remain sufficient without the registry.

**Consequences:** Familiar implementation and easy migration. Large-scale/distributed optimization is deferred.

## ADR-010 — `TASK.md` plus `STATUS.md` is the AI handoff mechanism

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** `TASK.md` is the durable backlog/evidence ledger. `STATUS.md` is the current overwrite-style checkpoint with exact next action. `DECISIONS.md` captures design changes.

**Consequences:** An agent can resume after a context limit. These files must be updated as part of implementation, not afterthought documentation.

## ADR-011 — Research conclusion labels are constrained

**Status:** Accepted  
**Date:** 2026-08-21

**Decision:** Reports use only the labels defined in `docs/06_EDGE_RESEARCH_PROTOCOL.md` and never state that an edge is guaranteed/proven.

**Consequences:** Results communicate uncertainty and reduce pressure to overstate in-sample findings.
