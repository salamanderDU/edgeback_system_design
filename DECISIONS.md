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

## ADR-012 — Intents carry bracket target; risk builds bracket orders

**Status:** Accepted  
**Date:** 2026-08-29

**Context:** docs/05 §7 specifies `OrderIntent` includes "target price/R-multiple where applicable", and docs/04 §4 lists bracket entry (stop-loss and take-profit children) as an MVP order type. The shipped `OrderIntent` had stop price but no target price, and the risk manager mapped intents to plain market/limit orders, so an end-to-end engine run could never exercise the T420 bracket semantics.

**Decision:** Add an additive optional `take_profit_price: float | None = None` to `OrderIntent`. The risk manager's `_build_entry_order` maps an intent with both `stop_price` and `take_profit_price` to a `bracket` order (`stop_loss_price`/`take_profit_price` children, filled by the T420 `SimulatedBroker`), otherwise to the existing market/limit mapping. ORB emits `take_profit_price = entry_reference +/- reward_risk * stop_distance` per its hypothesis spec. This is completing the documented contract, not changing engine semantics.

**Alternatives:** Keep intents stop-only and synthesize bracket children invisibly in the engine. Rejected: invisible transformation hides intent auditability (NFR-004).

**Consequences:** Strategies can declare both protective legs; the broker keeps full lifecycle control; prior tests remain valid because the new field is optional and defaults to `None`.

## ADR-013 — Multi-symbol engine: per-symbol strategy instances, broker symbol filter, and shared-capital allocator

**Status:** Accepted  
**Date:** 2026-08-29

**Context:** T450 must merge bars across symbols by `bar_end_utc`, evaluate fills in deterministic order, invoke `on_bar` per symbol in canonical symbol order, risk-check emitted intents as a batch against shared capital, and allocate simultaneous orders deterministically (docs/02 §7, docs/04 §12). Two implementation gaps block this:
1. `SimulatedBroker.on_bar` evaluates every open order against the given bar without checking `order.symbol == bar.symbol`. With multiple symbols a working order for one symbol could match (and fill on) another symbol's bar prices — a correctness bug for multi-symbol runs.
2. Strategies such as ORB store per-symbol session state in instance attributes without a symbol key (`self.state["trades_taken_by_direction"]`, `self.state["opening_range_high"]`). A single shared strategy instance across symbols would corrupt state across symbols. docs/05 §3 says `on_bar` is "invoked in deterministic symbol order" but does not specify instance-per-symbol; instance sharing is therefore ambiguous.

**Decision:**
- The multi-symbol engine keeps **one strategy instance per canonical symbol**, all built from the same configuration parameters. Each instance receives a `CausalStrategyContext` whose `bars_by_symbol` still contains the full multi-symbol causal bar set (history access to other symbols remains available and causally bounded).
- `SimulatedBroker.on_bar` and `on_bars` will evaluate only working orders whose `order.symbol` equals `bar.symbol`; the single-symbol behavior is unchanged because all orders share the symbol.
- Shared capital is enforced by evaluating all emitted intents at a timestamp as a **batch**: a deterministic `priority_then_symbol` allocator sorts candidate intents by (priority descending, canonical symbol ascending, intent creation order) and evaluates each against a projected portfolio state that reflects capital/exposure reservations made by earlier-accepted intents in the same batch. `priority` is declared on the intent (docs/05 §7 lists priority as an intent field); the engine sets `creation_order` by the per-symbol `on_bar` dispatch order. Rejected/resized decisions are recorded with reason codes exactly like single-symbol runs.
- Unknown `engine.entry_allocation` values fail fast at engine construction. `priority_then_symbol` is the only documented MVP allocator (docs/02 §7).

**Alternatives:**
- Share one strategy instance and key state by symbol. Rejected: it would require modifying every existing strategy's internal state convention and leaks per-symbol bookkeeping into strategy authors' responsibilities.
- Allocate sequentially without projection. Rejected: evaluation order would depend on the order intents were emitted, which depends on symbol dispatch order, breaking symbol-order-independent economics.
- Fix broker matching only, without an allocator. Rejected: shared-capital acceptance must be deterministic and disclosed (NFR-004).

**Consequences:** ORB and other per-symbol strategies run correctly unchanged in multi-symbol backtests. Strategy instances are still fresh per run (no module-level mutable state, docs/04 §2). The broker's symbol filter is a correctness fix, not a semantic change for single-symbol runs. The allocator is deterministic and disclosed; future allocators (`pro_rata`) may be added behind the same interface.

## ADR-014 — Engine-generated session-close liquidation derives close from the final bar; protective children are cancelled

**Status:** Accepted  
**Date:** 2026-08-29

**Context:** T460 must implement `docs/04_BACKTEST_ENGINE.md` §10: the engine generates a special liquidation event on the final regular-session bar, fills at the final close plus adverse costs, tags it `FORCED_SESSION_CLOSE`, and honors early closes via the calendar (no hard-coded 16:00). The engine loop already grouped bars by session; the canonical bar set is complete and the final bar of a session is, by construction, the bar that ends at the calendar-provided session close (a regular 16:00 ET close on normal days, 13:00 ET on early-close days). A second question was what happens to still-open bracket children when a position is force-flattened.

**Decision:**
- `SimulatedBroker.force_flat_at_close(positions, bar)` builds a deterministic market order per open position for `bar.symbol`, fills at `bar.close` (the documented ADR-007 exception, whose only trigger is the engine, never a strategy signal) with the normal T410 cost decomposition, tags the order and fill `FORCED_SESSION_CLOSE`, and cancels any still-open bracket children for that symbol with `FORCED_SESSION_CLOSE_PARENT` so they cannot fill later into the next session (NFR-004).
- Both engines call this after the per-session bar loop and after strategy dispatch, before `on_session_end` (matching docs/04 §13 `broker.force_flat_at_close(session.final_bar)`). The single-symbol engine liquidates once per session using its only final bar. The multi-symbol engine tracks session boundaries over the merged timestamp stream and liquidates each symbol using that symbol's own final bar in the session.
- The session-close price is taken **from the final bar of the data** (the calendar-provided close by construction). A separate calendar lookup is unnecessary because the engine only ever seeds bars that belong to a session's declared bars, and the design forbids hard-coding 16:00.
- When `engine.force_flat_at_session_end` is false (config override), no forced liquidation is generated and positions may remain open (a user-declared non-day-trade simulation). This is explicit in config and is the only way a position survives session end.

**Alternatives:**
- Query the trading calendar directly for the close time and synthesize a close event. Rejected: the engines receive canonical bars only, and introducing a calendar dependency into the engine layer would complicate offline determinism; the final bar *is* the calendar close.
- Leave bracket children working after a forced close. Rejected: a stale stop/target would fill in the next session for a position that no longer exists, breaking ledger reconciliation and artifact explainability.

**Consequences:** Day-trade default (`force_flat_at_session_end=true`) now fully matches docs/04 §7's "all positions are flat at the end of the configured session" and §10's forced liquidation semantics. Forced exits are visible in fills, orders, warnings, and broker events. Existing T440/T450 engine tests deliberately set `force_flat_at_session_end=false` so their pre-T460 fill-count assertions remain scoped to their own invariants; T460's dedicated `tests/unit/test_session_liquidation.py` covers the new behavior.
