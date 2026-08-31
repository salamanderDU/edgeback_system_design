# 05 — Strategy Plugin Specification

## 1. Objective

Strategies are replaceable research modules. A strategy decides **when and why it wants exposure**. It does not download data, calculate fill prices, change cash, bypass risk rules, or write artifacts.

Every strategy lives in one Python file under the trusted top-level `strategies/` package.

## 2. File and identity convention

```text
strategies/<strategy_id>.py
strategy_specs/<strategy_id>.yaml
strategies/__init__.py
```

Rules:

- `strategy_id` is lowercase snake_case and stable.
- Strategy code declares semantic `strategy_version`.
- Config references `strategy.name`, not a file path supplied by an untrusted user.
- Registry imports only the trusted `strategies` package; arbitrary filesystem imports are disabled.
- No ticker symbol may be embedded in strategy logic. Symbol-specific values belong in config.

## 3. Public contract

A typed contract should be equivalent to:

```python
class Strategy(ABC, Generic[ParamsT]):
    strategy_id: ClassVar[str]
    strategy_version: ClassVar[str]
    params_model: ClassVar[type[ParamsT]]

    @classmethod
    def metadata(cls) -> StrategyMetadata: ...

    def initialize(self, ctx: StrategyContext) -> None: ...
    def on_session_start(self, ctx: StrategyContext) -> None: ...
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]: ...
    def on_order_update(self, ctx: StrategyContext, event: OrderEvent) -> None: ...
    def on_session_end(self, ctx: StrategyContext) -> list[OrderIntent]: ...
    def finalize(self, ctx: StrategyContext) -> None: ...
```

`on_bar` receives a bar only after it is complete. In multi-symbol runs it is invoked in deterministic symbol order. A future portfolio strategy may receive `on_timestamp(ctx, bars)` behind a declared `scope=portfolio` contract.

## 4. Strategy metadata

Required metadata:

- strategy ID and version;
- human-readable name and description;
- supported markets/timeframes;
- supported directions;
- scope: `per_symbol` or `portfolio`;
- required fields/features;
- warmup bars/sessions;
- whether previous-session data is required;
- parameter schema;
- research status: `hypothesis`, `experimental`, or `validated_for_dataset`;
- known limitations.

The status `validated_for_dataset` is not a statement of future profitability and must name the dataset/research report.

## 5. Parameter model

Each module defines a strict Pydantic parameter model. Requirements:

- unknown keys rejected;
- ranges and cross-field constraints validated;
- times use explicit exchange-local `HH:MM` values;
- percentages have unambiguous units in names, such as `_pct` or `_bps`;
- defaults are conservative and documented;
- no provider credentials or paths in strategy parameters.

## 6. Read-only causal context

Allowed context capabilities:

- current engine time and session metadata;
- current symbol/bar;
- causal historical bars up to current time;
- read-only position and portfolio snapshot;
- session counters and prior fills/orders for this strategy;
- pure feature helpers;
- intent factory methods;
- structured strategy logging.

Forbidden capabilities:

- future bars or full unmasked DataFrame;
- direct portfolio mutation;
- direct broker/fill calls;
- filesystem/network access;
- environment variables/secrets;
- report/database writes;
- global mutable state.

The context layer must enforce time boundaries rather than trusting strategy authors.

## 7. Intent model

An `OrderIntent` includes:

- strategy ID/version;
- symbol and side;
- intent type: entry, exit, reduce, cancel;
- order type and price fields;
- optional desired quantity or sizing instruction;
- stop price/distance and target price/R-multiple where applicable;
- time-in-force/session expiration;
- priority;
- reason code and concise rationale;
- signal timestamp;
- feature snapshot needed for audit.

Strategies should usually request a sizing method rather than compute final share quantity. The risk manager owns final sizing.

## 8. State rules

Strategy instance state may contain only values necessary for behavior, such as the opening-range high/low or whether a trade was taken this session. State must be serializable to JSON-compatible structures for debugging/checkpoints.

State resets must be explicit. Session state must not accidentally leak into the next day.

## 9. Feature rules

Reusable indicators are pure causal functions under `src/edgeback/features/`. A feature computed at bar `T` may use only bars ending at or before `T`.

- Rolling windows specify minimum periods.
- VWAP resets according to the declared session.
- ATR and prior-close logic define gap/session behavior.
- No centered windows.
- No negative shifts.
- No global normalization using future samples.

Each strategy test includes a future-data mutation test: changing bars after time `T` must not change signals at or before `T`.

## 10. Strategy implementation template

The final repository should provide a compileable template similar to:

```python
@register_strategy
class ExampleStrategy(Strategy[ExampleParams]):
    strategy_id = "example_strategy"
    strategy_version = "0.1.0"
    params_model = ExampleParams

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            scope="per_symbol",
            warmup_bars=20,
            required_fields=("open", "high", "low", "close", "volume"),
            research_status="hypothesis",
        )

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[OrderIntent]:
        history = ctx.history(bar.symbol, bars=20)
        if len(history) < 20:
            return []
        # Causal hypothesis logic only; risk manager determines final size.
        return []
```

## 11. Adding a strategy

1. Add a hypothesis file under `strategy_specs/`.
2. Add one module under `strategies/`.
3. Define strict parameters and metadata.
4. Register the strategy.
5. Add unit tests for entries, exits, warmup, session reset, and no-look-ahead.
6. Add a tiny golden backtest fixture.
7. Verify `edgeback strategies list` and `edgeback strategies describe <id>`.
8. Update `TASK.md` and the strategy research status.

No engine edit should be necessary. If it is, the strategy is depending on missing general capability; add that capability through an interface and record an ADR.

## 12. Seed strategies

The design bundle includes three hypothesis specs:

- `opening_range_breakout`
- `vwap_mean_reversion`
- `gap_momentum`

They are test cases and research starting points, not proven edges. Implement ORB first because it exercises session state, time windows, bracket exits, and next-bar timing without requiring a second data feed.

