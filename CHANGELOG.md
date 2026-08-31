# Changelog

## 0.1.0 — 2026-08-31

Initial EdgeBack MVP implementation.

- Strict, frozen YAML configuration with safe CLI overrides.
- Canonical timezone-aware bar model, validation, local import, yfinance and Alpaca IEX adapters.
- Deterministic causal event engine with multi-symbol shared capital.
- Market, limit, stop and bracket simulation with explicit spread, slippage, commissions and ambiguity policy.
- Risk sizing/limits, long-short portfolio accounting and end-of-session liquidation.
- Three isolated seed strategies: opening-range breakout, VWAP mean reversion and gap momentum.
- Immutable run artifacts, SQLite registry, metrics, checksums and self-contained HTML report.
- Session-based sweep, final holdout, walk-forward, cost stress, concentration checks and bootstrap.
- Typer CLI and complete offline fixture acceptance workflow.
