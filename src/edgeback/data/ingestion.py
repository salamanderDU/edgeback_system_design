"""Explicit provider acquisition -> normalization -> validation -> canonical repository service."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any


from edgeback.calendar import XNYSCalendar
from edgeback.config.models import ResolvedConfig
from edgeback.data.manifest import DatasetManifest
from edgeback.data.normalization import normalize_provider_frame
from edgeback.data.providers import AlpacaIEXProvider, LocalFileProvider, YFinanceProvider
from edgeback.data.providers.interfaces import BarRequest, MarketDataProvider
from edgeback.data.repository import DataRepository
from edgeback.domain import Bar
from edgeback.errors import DataUnavailableError, DataValidationError


def provider_from_id(provider_id: str) -> MarketDataProvider:
    if provider_id == "yfinance":
        return YFinanceProvider()
    if provider_id == "alpaca":
        return AlpacaIEXProvider()
    raise DataUnavailableError(f"No network provider adapter registered for {provider_id!r}")


def provider_capabilities() -> tuple[dict[str, Any], ...]:
    providers: tuple[MarketDataProvider, ...] = (
        YFinanceProvider(),
        AlpacaIEXProvider(),
        LocalFileProvider(),
    )
    return tuple(item.describe_capabilities().model_dump(mode="json") for item in providers)


def _utc_request_range(config: ResolvedConfig) -> tuple[datetime, datetime]:
    date_range = config.data.date_range
    assert date_range.start is not None and date_range.end is not None
    return (
        datetime.combine(date_range.start, time.min, tzinfo=UTC),
        datetime.combine(date_range.end + timedelta(days=1), time.min, tzinfo=UTC),
    )


def _regular_session_filter(bars: tuple[Bar, ...], calendar: XNYSCalendar) -> tuple[Bar, ...]:
    kept: list[Bar] = []
    for bar in bars:
        if not calendar.is_session(bar.session_date):
            continue
        session = calendar.session(bar.session_date)
        if bar.bar_start_utc >= session.open_utc and bar.bar_end_utc <= session.close_utc:
            kept.append(bar)
    return tuple(kept)


def acquire_and_ingest(config: ResolvedConfig) -> DatasetManifest:
    if config.data.provider == "local":
        raise DataUnavailableError("Use `edgeback data import` for provider=local")
    provider = provider_from_id(config.data.provider)
    calendar = XNYSCalendar()
    start_utc, end_utc = _utc_request_range(config)
    request = BarRequest(
        symbols=config.data.symbols,
        interval=config.data.interval,
        start_utc=start_utc,
        end_utc=end_utc,
        feed=config.data.feed,
        include_extended_hours=config.market.include_extended_hours,
        adjustment_mode=config.data.adjustment_mode,
    )
    raw = provider.fetch_bars(request)
    frame = raw.dataframe()
    if "symbol" not in frame.columns:
        if len(config.data.symbols) != 1:
            raise DataValidationError("Provider payload lacks symbol column for a multi-symbol request")
        frame = frame.assign(symbol=config.data.symbols[0])
    normalized: list[Bar] = []
    for canonical in sorted(config.data.symbols):
        provider_symbol = provider.resolve_symbol(canonical).provider_symbol
        candidates = frame.loc[frame["symbol"].astype(str).str.upper().isin({canonical, provider_symbol.upper()})]
        if candidates.empty:
            raise DataUnavailableError(f"Provider returned no rows for {canonical}")
        normalized.extend(
            normalize_provider_frame(
                candidates.reset_index(drop=True),
                symbol=canonical,
                provider_symbol=provider_symbol,
                provider=config.data.provider,
                feed=config.data.feed,
                interval_seconds=config.data.interval_seconds,
                timestamp_column="timestamp",
                timestamp_semantics="bar_start",
                source_timezone="UTC",
                adjustment_mode=config.data.adjustment_mode,
                session_type=config.market.session,
            )
        )
    bars = tuple(sorted(normalized, key=lambda item: (item.bar_end_utc, item.symbol)))
    if not config.market.include_extended_hours:
        bars = _regular_session_filter(bars, calendar)
    repository = DataRepository(config.data.cache_dir)
    capabilities = provider.describe_capabilities()
    return repository.ingest(
        bars,
        calendar=calendar,
        capabilities=capabilities,
        minimum_session_completeness_pct=config.data.minimum_session_completeness_pct,
        missing_session_policy=config.data.missing_session_policy,
        requested_start_utc=start_utc,
        requested_end_utc=end_utc,
        raw_request_ids=(raw.request_id,),
        licensing_warning="; ".join(capabilities.limitations),
    )
