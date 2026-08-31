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

