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

