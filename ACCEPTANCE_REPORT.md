# EdgeBack 0.1.0 Acceptance Report

**Date:** 2026-08-31  
**Environment:** Python 3.13.5, offline/no provider credentials

## Completed validation

- `PYTHONPATH=src:. pytest -q -m 'not network' -W error::ResourceWarning` → **56 passed, 2 deselected**, with resource warnings treated as errors.
- `python -m compileall -q src strategies templates benchmarks` → **passed**.
- Coverage run → **86% overall**; event engine 93%, broker 92%, portfolio ledger 95%, config models 94%, metrics 93%.
- Custom AST import-use scan → **passed**; no unused imports found outside deliberate optional-import probes.
- Forbidden-shortcut scan → no `eval`/`exec` and no common tradable-symbol literals in `src/edgeback` or `strategies`.
- `python -m pip wheel . --no-deps --no-build-isolation` → **wheel built and installed into an isolated target**; package version and all three trusted strategies imported.
- Release wheel SHA-256: `c7d4868001a822c1a9c4ab88aeeef0d1f75c016a67dbbf18bd0c0b5ed8092a31`.
- Small non-CI benchmark: 780 bar events, status `COMPLETED`, portfolio reconciled by the engine.

## Clean-directory offline workflow

The following commands were run with a temporary config whose data/run roots were outside the repository:

```bash
python -m edgeback doctor -c /tmp/edgeback_acceptance/config.yaml
python -m edgeback strategies list
python -m edgeback strategies describe opening_range_breakout
python -m edgeback data validate -c /tmp/edgeback_acceptance/config.yaml --fixture
python -m edgeback backtest run -c /tmp/edgeback_acceptance/config.yaml --fixture
python -m edgeback runs list --output-dir /tmp/edgeback_acceptance/runs
python -m edgeback report build <run_id> --output-dir /tmp/edgeback_acceptance/runs
```

Observed:

- doctor: `PASS`
- strategy count: 3
- fixture validation: `PASS`
- three immutable run records created (two equivalent runs plus one symbol override)
- symbol override resolved to `ZZZ` without changing strategy code
- derived report created outside the immutable run directory
- two equivalent runs produced identical SHA-256 values for intents, orders, fills, trades, equity, metrics and gate results

## Mechanics covered by tests

- no same-bar signal fill; next-open market execution
- future-data masking and mutation invariance
- warmup isolation and research trade windows
- market/limit/stop/bracket fills, limit improvement and gap-through stop
- all four same-bar ambiguity policies
- missing-next-bar expiry without backfill
- normal and XNYS early-close forced liquidation
- shared-capital multi-symbol ordering and reconciliation
- spread/slippage/commission decomposition and leverage guard
- timezone, OHLC, duplicates, incomplete/missing bars and mixed feed validation
- atomic data/run/research child writes, checksums, tamper detection and overwrite refusal
- zero/undefined metrics, constrained conclusion labels, sweep/final holdout and walk-forward
- mocked yfinance and Alpaca adapters; optional live tests are marked `network`

## Environment-blocked release gates

The implementation environment did not contain Ruff, mypy or PyArrow, and package-network access was disabled. Therefore these exact commands/genuine backend path could not be executed here:

```bash
ruff check .
ruff format --check .
mypy src
# genuine PyArrow Parquet integration
```

They are declared in `pyproject.toml`, configured in `.github/workflows/ci.yml`, and listed as required release gates. The local table fallback is explicitly marked with a non-Parquet magic header and is never reported as genuine Parquet.

Live provider smoke tests were not executed because network access and Alpaca credentials were unavailable. Mocked provider tests and opt-in network test definitions are included.
