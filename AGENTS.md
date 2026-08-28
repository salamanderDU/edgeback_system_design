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
