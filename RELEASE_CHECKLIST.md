# EdgeBack 0.1.0 Release Checklist

## Required before publishing

- [x] Package imports from the `src/` layout.
- [x] Offline tests pass without API keys or network access.
- [x] No tradable symbol is hard-coded in core or strategy logic.
- [x] Signal-close orders cannot fill before the next bar.
- [x] Same-bar stop/target policy is explicit and tested.
- [x] Normal and early-close forced liquidation are tested.
- [x] Data validation rejects timezone ambiguity, invalid OHLC, duplicates, incomplete bars and mixed feeds.
- [x] Completed run artifacts have checksums and overwrite protection.
- [x] Research selection uses train/validation only and keeps final-test identity.
- [x] Secrets are environment-only and redacted from logs/doctor output.
- [x] Documentation and example configurations match version 0.1.0.
- [ ] Run `ruff check .`, `ruff format --check .`, and `mypy src` in an environment with dev dependencies installed.
- [ ] Exercise genuine PyArrow Parquet I/O in an environment with `pyarrow` installed.
- [ ] Optionally run marked network smoke tests after re-verifying provider plans and limits.

The final three unchecked items are environment-dependent validation gates, not missing implementation modules.
