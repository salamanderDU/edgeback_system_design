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

## ADR-012 — Use `exchange_calendars` behind the XNYS interface

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** The design requires an XNYS-compatible calendar and forbids fixed UTC offsets. The implementation environment already provides the maintained `exchange_calendars` package, while `pandas_market_calendars` was unavailable.

**Decision:** Implement `XNYSCalendar` with `exchange_calendars`, keeping all engine/data code dependent only on the project `TradingCalendar` interface.

**Consequences:** Holidays, daylight saving and early closes remain calendar-driven. The backend can be replaced without changing strategies or the event engine.

## ADR-013 — Normalize multi-symbol batch events globally

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** Per-symbol broker evaluation can discover an intrabar touch at a bar end before another symbol's next-open execution at the same timestamp group. Assigning IDs during discovery can therefore conflict with chronological ledger invariants.

**Decision:** Evaluate bars in canonical-symbol order, then normalize fills/events/warnings for the complete same-timestamp batch by event time, priority, symbol and creation sequence before applying them to the shared portfolio.

**Consequences:** IDs and accounting remain deterministic and chronological without changing fill economics.

## ADR-014 — Production Parquet with an explicit constrained-test fallback

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** PyArrow is a required production dependency, but the implementation environment had no PyArrow wheel and no package-network access.

**Decision:** Use genuine PyArrow Parquet whenever installed. In a constrained development environment only, use a deterministic JSON-table payload carrying an EdgeBack-specific magic header and record the storage format explicitly. Never represent the fallback as genuine Parquet.

**Consequences:** Offline mechanics can be tested here, while release users installing declared dependencies receive canonical Parquet. The genuine Parquet path remains an external release gate.

## ADR-015 — Research windows use earlier sessions only as causal warmup

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** Validation/test windows need prior bars for indicators, while trades and metrics must not leak outside the selected sessions.

**Decision:** The engine accepts an explicit set of trade-session dates. Earlier bars advance causal strategy history but suppress intents and performance accounting for the evaluation window.

**Consequences:** Train, validation, final test and walk-forward folds share the production engine while preserving warmup isolation.

## ADR-016 — Define `opposite_range_or_atr` as the tighter valid protective stop

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** The ORB hypothesis named a combined range/ATR stop but did not specify the operator when both references are valid.

**Decision:** For long entries use the higher of opening-range low and ATR stop; for short entries use the lower of opening-range high and ATR stop. This selects the closer adverse stop while preserving a positive stop distance.

**Consequences:** Risk is conservative in capital usage and deterministic. This choice is versioned as ORB 0.1.0 and must change strategy version if altered.

## ADR-017 — Rebuilt reports are derived artifacts

**Status:** Accepted  
**Date:** 2026-08-31

**Context:** Completed run directories must not be mutated, but users may need to regenerate a report from stored tables and metrics.

**Decision:** `edgeback report build` writes to `runs/derived_reports/` instead of replacing `report.html` inside the completed run.

**Consequences:** Run checksums and immutability remain intact; derived reports can be deleted/rebuilt independently.
