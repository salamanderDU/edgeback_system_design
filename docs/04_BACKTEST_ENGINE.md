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
