# 09 — Free Intraday Data Sources and Upgrade Path

Verified for design purposes on **2026-08-21**. Provider plans and limits can change; the implementation must re-check capabilities and store a capability snapshot in each data manifest.

## 1. Starting matrix

| Provider | Cost/start requirement | Useful scope | Important limitation | EdgeBack role |
|---|---|---|---|---|
| yfinance / Yahoo public endpoints | No key; Python package | Recent 1m/2m/5m/15m/etc. stock bars | yfinance documents that intraday history cannot extend beyond the latest 60 days; it is unofficial and intended for research/personal use subject to Yahoo terms | Default smoke-test/recent-data adapter |
| Alpaca Market Data Basic, IEX feed | Free account and API keys | US stock/ETF historical data since 2016 according to Alpaca plan docs | Free equity feed is IEX rather than consolidated SIP; the Basic plan documents a latest-15-minute historical-data restriction and 200 historical API calls/minute. Alpaca describes IEX as a small fraction of total US market volume, so volume and some price behavior differ from whole-market data | Optional longer-history adapter; disclose `feed=iex` prominently |
| Local CSV/Parquet | Depends on user-supplied source | Any data that can be mapped to canonical schema | Quality, licensing, timestamp semantics, adjustments, and survivorship depend on the source | First-class import and future paid-data upgrade path |
| Alpha Vantage | API key; plan-dependent | Intraday endpoint exists | Current official documentation marks `TIME_SERIES_INTRADAY` as Premium; do not assume it is a free MVP source | Optional future adapter only after plan verification |

## 2. Recommended MVP sequence

### Step 1 — Local fixtures

Implement and validate the entire engine using hand-built fixture data. This prevents provider quirks from hiding engine bugs.

### Step 2 — yfinance

Use for installation smoke tests and recent 5m research. Request explicit parameters; never rely on library defaults for adjustment or extended hours. Cache immediately and record the package version, request, source, and limitation warning.

### Step 3 — Alpaca IEX

Add for longer historical experiments. Require `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` through environment variables. Record `source_feed=iex`. Do not compare IEX volume-sensitive results directly with consolidated/Yahoo results as though they were the same dataset.

### Step 4 — Local paid/consolidated import

When research justifies spending, import a higher-quality dataset through the canonical CSV/Parquet adapter. Engine and strategy code remain unchanged.

## 3. Provider-selection policy

- Provider/feed is explicit in config.
- No fallback from one provider to another.
- No stitching providers into one symbol history by default.
- Dataset and report names include provider/feed.
- Research comparisons use the same provider/feed or clearly separate the result.
- Rate limits and latest-bar delays are stored in capability metadata.

## 4. What free OHLCV cannot model well

- true bid/ask spread and queue position;
- consolidated volume when using a single-exchange feed;
- market impact for larger orders;
- halts and detailed auction behavior;
- borrow availability and short locate fees;
- exact order path inside each bar;
- point-in-time universe membership and delisted symbols;
- corporate-action-perfect history.

The report must state these limitations. Synthetic cost stress is mandatory but cannot fully replace quote/tick data.

## 5. Data-quality comparison procedure

Before changing the primary provider:

1. Download overlapping sessions for a liquid symbol.
2. Compare bar counts, open/high/low/close differences, volume ratios, missing bars, split handling, and session boundaries.
3. Run the same fixed strategy/config against each provider as separate datasets.
4. Attribute differences to data source rather than treating them as strategy improvements.
5. Record the decision in `DECISIONS.md`.

## 6. Official references

- yfinance download reference: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- yfinance legal/project disclaimer: https://ranaroussi.github.io/yfinance/
- Alpaca market-data plan overview: https://docs.alpaca.markets/us/docs/about-market-data-api
- Alpaca historical stock feed description: https://docs.alpaca.markets/us/docs/historical-stock-data-1
- Alpha Vantage API documentation: https://www.alphavantage.co/documentation/

These references are implementation inputs, not permanent guarantees. Re-verify before coding provider-specific assumptions.

