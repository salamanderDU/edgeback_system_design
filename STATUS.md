# STATUS.md — Current Project Checkpoint

**Last updated:** 2026-08-31 (Asia/Singapore)  
**Project state:** IMPLEMENTATION_COMPLETE_EXTERNAL_GATES_PENDING  
**Current milestone:** M8 — Hardening, documentation, and MVP acceptance  
**Current task:** T830 — Release and safe handoff  
**Current task status:** BLOCKED only on unavailable external quality/backend validation  
**Working tree:** Complete source implementation, tests, documentation, wheel, and release materials are present. Runtime data, generated runs, caches, and build directories are excluded from the release archive.

## Current objective

Deliver EdgeBack 0.1.0 as a complete deterministic intraday backtesting and edge-research system while recording the exact validation that was possible in this offline environment and the remaining external gates honestly.

## Implementation completed

- Strict, frozen Pydantic configuration; safe YAML loading; symbol and strategy-parameter CLI overrides; stable configuration hashing.
- Typed domain models, XNYS calendar support, canonical market-data validation/normalization, manifests, local import, yfinance, and Alpaca IEX adapters.
- Causal strategy context and trusted registry with separate ORB, session-VWAP mean-reversion, and gap-momentum strategy modules.
- Deterministic single- and multi-symbol event engine with next-bar signal fills, explicit market/limit/stop/bracket behavior, four ambiguity policies, costs, risk sizing/limits, shared capital, portfolio reconciliation, and calendar-driven session liquidation.
- Stable result tables, cost-inclusive metrics, atomic immutable run artifacts, checksums/tamper verification, SQLite registry, and self-contained HTML reporting.
- Chronological train/validation/test splits, deterministic sweeps, rolling/anchored walk-forward, cost/delay/parameter robustness, session bootstrap, concentration checks, and constrained conclusion labels.
- Full Typer CLI, offline fixtures, mocked provider tests, opt-in live provider tests, CI configuration, documentation, release checklist, source release, and wheel.

## Validation performed

- `PYTHONPATH=src:. pytest -q -m 'not network' -W error::ResourceWarning` → **56 passed, 2 deselected**.
- `python -m compileall -q src strategies templates benchmarks` → passed.
- Coverage run → **86% overall**; event engine 93%, broker 92%, portfolio ledger 95%, configuration models 94%, metrics 93%.
- Custom AST import-use and forbidden-shortcut scans → passed: no core `eval`/`exec`, no unsafe YAML loading, no common hard-coded tradable-symbol literals in `src/edgeback` or `strategies`, and network imports are confined to provider adapters.
- Clean-directory CLI workflow → doctor PASS, three strategies discovered, fixture validation PASS, immutable backtest artifacts and report created, CLI symbol replacement resolved correctly.
- Two logically equivalent clean-directory runs produced identical SHA-256 values for canonical intents, orders, fills, trades, equity, metrics, and gate results.
- Wheel built and installed into an isolated target; version 0.1.0 and all three trusted strategy plugins imported successfully.
- Wheel SHA-256: `c7d4868001a822c1a9c4ab88aeeef0d1f75c016a67dbbf18bd0c0b5ed8092a31`.

## External blockers

- This execution environment has no package-network access and does not contain Ruff, mypy, or PyArrow. Therefore `ruff check .`, `ruff format --check .`, `mypy src`, and the genuine PyArrow Parquet backend could not be executed here.
- The project declares and configures those dependencies/gates in `pyproject.toml` and `.github/workflows/ci.yml`. The constrained local table fallback has a distinct non-Parquet magic header and never claims to be genuine Parquet.
- Live yfinance/Alpaca smoke tests were not run because network access is disabled and Alpaca credentials are absent. Mocked tests and opt-in tests marked `network` are included.

## Exact next actions in a connected Python 3.12 environment

```bash
python -m pip install -e '.[dev]'
pytest -m 'not network' -W error::ResourceWarning
ruff check .
ruff format --check .
mypy src
pytest -m network tests/network  # optional; requires network and provider credentials
```

Then run the release checklist and change T010, T800, and T830 from `BLOCKED` to `DONE` only after the unavailable gates pass. T810 may remain `BLOCKED` when live provider access is intentionally unavailable.

## Resume note

Safe to resume. No implementation file is half-written. All known environment limitations are explicit, generated runtime directories are ignored, and the release archive can be independently extracted and tested offline.
