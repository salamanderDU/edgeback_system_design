# 03 — Data Layer

## 1. Principles

1. Provider-native data is not engine data.
2. Fetching, normalization, validation, and simulation are separate steps.
3. A dataset has a stable ID and manifest.
4. No provider or feed is silently substituted.
5. No OHLCV gap is silently forward-filled.
6. Every timestamp has explicit timezone semantics.
7. A backtest is offline by default.

## 2. Provider interface

A provider adapter implements behavior equivalent to:

```python
class MarketDataProvider(Protocol):
    provider_id: str

    def describe_capabilities(self) -> ProviderCapabilities: ...
    def resolve_symbol(self, canonical_symbol: str) -> ProviderSymbol: ...
    def fetch_bars(self, request: BarRequest) -> RawBarBatch: ...
    def fetch_actions(self, request: ActionRequest) -> RawActionBatch: ...
```

`BarRequest` includes symbols, interval, exact UTC/local range, session inclusion, adjustment request, feed, and paging controls. Provider retries are bounded and recorded. Rate-limit sleeps must be observable in logs.

Provider adapters may not write directly into canonical storage. They return raw batches plus metadata to the ingestion service.

## 3. Storage zones

```text
data/
├── raw/<provider>/<request_id>/
│   ├── payload.*
│   └── request_metadata.json
├── canonical/bars/
│   └── provider=<id>/feed=<id>/interval=<n>/symbol=<ticker>/year=<yyyy>/month=<mm>/*.parquet
├── manifests/<dataset_id>.json
└── validation/<dataset_id>.json
```

The raw zone is optional for providers whose terms or response format make storage inappropriate, but request metadata remains mandatory. The canonical zone is required.

Canonical files are append-safe and deduplicated by `(symbol, interval, bar_start_utc)`. Ingestion must write temporary files and atomically replace partitions.

## 4. Canonical bar schema

The authoritative machine-readable schema is `schemas/bar.schema.json`. Parquet should use these logical meanings:

| Field | Type | Required | Meaning |
|---|---:|:---:|---|
| `symbol` | string | yes | Canonical symbol, uppercase |
| `provider_symbol` | string | yes | Symbol sent to provider |
| `interval_seconds` | int32 | yes | Bar duration |
| `bar_start_utc` | timestamp UTC | yes | Inclusive interval start |
| `bar_end_utc` | timestamp UTC | yes | Exclusive interval end; strategy event time |
| `session_date` | date | yes | Exchange-local trading date |
| `session_type` | enum | yes | `regular`, `pre`, `post`, or `overnight` |
| `open/high/low/close` | float64 | yes | Normalized price fields |
| `volume` | int64 | yes | Nonnegative provider-reported volume |
| `vwap` | float64 nullable | no | Provider-reported or null; never silently synthesized |
| `trade_count` | int64 nullable | no | Provider-reported count or null |
| `is_complete` | bool | yes | Incomplete current bar must not be used |
| `source_provider` | string | yes | Provider ID |
| `source_feed` | string | yes | Feed ID such as `yahoo` or `iex` |
| `adjustment_mode` | enum | yes | `raw`, `split_adjusted`, or explicitly named mode |
| `ingested_at_utc` | timestamp UTC | yes | Acquisition timestamp |

`bar_end_utc - bar_start_utc` must equal `interval_seconds`. A strategy receives a bar only at `bar_end_utc` and only when `is_complete=true`.

## 5. Dataset manifest

Every canonical dataset has a JSON manifest containing at least:

- dataset ID and schema version;
- provider and feed;
- provider capability snapshot;
- canonical/provider symbols;
- interval and requested/actual coverage;
- session types included;
- exchange calendar ID and version metadata when available;
- adjustment mode and corporate-action handling;
- row counts per symbol/session;
- missing/duplicate/invalid bar counts;
- raw request IDs;
- partition checksums and aggregate hash;
- ingestion code version and timestamp;
- validation result and warnings;
- licensing/usage warning applicable to the provider.

A backtest references one or more compatible dataset IDs. Mixed providers/feeds require an explicit multi-dataset research plan and are forbidden inside a single symbol series.

## 6. Timezone and session rules

- Persist UTC timestamps.
- Convert through a calendar service, not fixed UTC offsets.
- US session decisions use `America/New_York` and an XNYS-compatible calendar.
- Handle holidays, daylight saving, and early closes from the calendar.
- Never create bars across a session boundary.
- When resampling 1m data to 5m/15m, group within a session and require a configured completeness threshold. Default: all expected component bars must exist.
- Drop or quarantine the latest provider bar when it is not complete.

## 7. Corporate actions and adjustments

Provider defaults must never be trusted implicitly. Each adapter passes explicit adjustment arguments and records the observed mode.

MVP policy:

- Prefer split-adjusted intraday bars for long history so splits do not create artificial gaps.
- Do not dividend-adjust intraday execution prices unless the provider supplies only a combined adjusted series and the limitation is documented.
- Preserve raw provider fields when allowed.
- When adjustment provenance is ambiguous, validation fails rather than guessing.
- Do not combine raw and adjusted partitions.

Because day trades close within a session, dividends rarely affect an individual trade, but inconsistent historical adjustment can corrupt indicators and comparative statistics.

## 8. Data validation gates

Validation produces `PASS`, `PASS_WITH_WARNINGS`, or `FAIL` and checks:

### Schema and types

- required columns present;
- timestamps timezone-aware;
- finite numeric values;
- symbol/feed/interval consistent.

### OHLC invariants

- prices greater than zero for the initial supported universe;
- `high >= max(open, close)`;
- `low <= min(open, close)`;
- `high >= low`;
- volume and trade count nonnegative.

### Temporal integrity

- sorted by symbol/time;
- unique key;
- duration matches interval;
- no bars from the future;
- no incomplete bars;
- no overlapping bars;
- bars belong to declared session.

### Coverage

- requested start/end compared with actual;
- missing expected bars by session;
- unexpected bars outside calendar;
- long gaps summarized;
- sessions with low completeness flagged.

Default missing-bar policy is `fail_session`: a session below the configured completeness threshold is excluded from research and listed explicitly. No price forward fill is allowed.

### Statistical sanity

- extreme returns and zero-volume sequences flagged, not automatically deleted;
- suspicious constant prices flagged;
- split-like discontinuities cross-checked against action metadata when available.

## 9. Local import provider

CSV/Parquet import is a first-class provider and the upgrade path for paid data. Import config must map source columns to the canonical schema and state timestamp semantics (`bar_start` or `bar_end`), timezone, adjustment mode, feed, and session type.

The importer must reject ambiguous timestamps. It may not infer local timezone from the developer machine.

## 10. Backtest data access

The engine receives a `DataSlice`/iterator from `DataRepository`, not a raw DataFrame owned by a strategy. Strategy context permits only current and past data.

A causal history API should look conceptually like:

```python
ctx.history(symbol="NVDA", bars=20, fields=["close", "volume"], include_current=True)
```

The repository enforces that the returned maximum `bar_end_utc` is not later than the engine clock. A sentinel test must prove that a future row cannot be read.

## 11. No implicit network rule

`edgeback backtest run` fails with a clear message when required canonical data is absent. It does not download automatically. A deliberate `--allow-download` option may be added later, but must default to false and must resolve a new data manifest before simulation.

## 12. Provider-specific cautions

- yfinance is convenient for recent research but documents a limited intraday lookback and personal-use considerations.
- Alpaca Basic provides a free IEX feed rather than consolidated US-market volume; price/volume-sensitive results must disclose that feed.
- Provider limits can change. Capabilities are queried or documented at ingestion time and stored in the manifest.

See `docs/09_FREE_DATA_SOURCES.md` for the verified starting matrix.

