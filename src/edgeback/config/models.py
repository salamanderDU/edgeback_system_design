"""Strict immutable configuration models."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Interval = Literal["1m", "5m", "15m"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ProjectConfig(StrictModel):
    name: str = "edgeback_run"
    tags: tuple[str, ...] = ()
    notes: str = ""
    random_seed: int = 42


class MarketConfig(StrictModel):
    calendar: str = "XNYS"
    timezone: str = "America/New_York"
    session: Literal["regular", "pre", "post", "overnight"] = "regular"
    include_extended_hours: bool = False


class DateRangeConfig(StrictModel):
    mode: Literal["explicit", "rolling"]
    start: date | None = None
    end: date | None = None
    lookback_calendar_days: int | None = Field(default=None, gt=0, le=36500)

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.mode == "explicit":
            if self.start is None or self.end is None:
                raise ValueError("explicit date range requires start and end")
            if self.lookback_calendar_days is not None:
                raise ValueError("explicit date range cannot set lookback_calendar_days")
            if self.start > self.end:
                raise ValueError("date range start must not be after end")
        else:
            if self.start is not None:
                raise ValueError("rolling date range cannot set start")
            if self.lookback_calendar_days is None:
                raise ValueError("rolling date range requires lookback_calendar_days")
        return self

    def resolve(self, *, today: date) -> "DateRangeConfig":
        if self.mode == "explicit":
            return self
        resolved_end = self.end or today
        assert self.lookback_calendar_days is not None
        return DateRangeConfig(
            mode="explicit",
            start=resolved_end - timedelta(days=self.lookback_calendar_days),
            end=resolved_end,
        )


class DataConfig(StrictModel):
    provider: Literal["yfinance", "alpaca", "local"] = "yfinance"
    feed: str = "yahoo"
    symbols: tuple[str, ...]
    interval: Interval = "5m"
    date_range: DateRangeConfig
    adjustment_mode: Literal["raw", "split_adjusted", "all_adjusted"] | str = (
        "split_adjusted"
    )
    cache_dir: Path = Path("data")
    minimum_session_completeness_pct: float = Field(default=98.0, ge=0.0, le=100.0)
    missing_session_policy: Literal["fail_session", "warn", "fail_dataset"] = "fail_session"
    allow_incomplete_latest_bar: bool = False
    dataset_id: str | None = None

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            value = [value]
        normalized = tuple(dict.fromkeys(str(item).strip().upper() for item in value if str(item).strip()))
        if not normalized:
            raise ValueError("at least one symbol is required")
        for symbol in normalized:
            if any(character.isspace() for character in symbol):
                raise ValueError(f"invalid symbol containing whitespace: {symbol!r}")
        return normalized

    @model_validator(mode="after")
    def validate_provider_feed(self) -> Self:
        if self.provider == "yfinance" and self.feed.lower() != "yahoo":
            raise ValueError("yfinance provider requires feed=yahoo")
        if self.provider == "alpaca" and self.feed.lower() != "iex":
            raise ValueError("Alpaca free adapter requires feed=iex")
        return self

    @property
    def interval_seconds(self) -> int:
        return {"1m": 60, "5m": 300, "15m": 900}[self.interval]


class EngineConfig(StrictModel):
    initial_cash_usd: float = Field(default=100_000.0, gt=0)
    signal_time: Literal["bar_close"] = "bar_close"
    market_fill_timing: Literal["next_bar_open"] = "next_bar_open"
    same_bar_bracket_policy: Literal[
        "stop_first", "target_first", "nearest_to_open", "reject_ambiguous_bar"
    ] = "stop_first"
    force_flat_at_session_end: bool = True
    entry_allocation: Literal["priority_then_symbol"] = "priority_then_symbol"
    fractional_shares: bool = False
    max_leverage: float = Field(default=1.0, ge=1.0, le=10.0)
    additional_entry_delay_bars: int = Field(default=0, ge=0, le=100)


class SpreadConfig(StrictModel):
    model: Literal["zero", "fixed_bps"] = "fixed_bps"
    full_spread_bps: float = Field(default=2.0, ge=0.0, le=10_000.0)


class SlippageConfig(StrictModel):
    model: Literal["zero", "fixed_bps"] = "fixed_bps"
    bps_per_side: float = Field(default=1.0, ge=0.0, le=10_000.0)


class CommissionConfig(StrictModel):
    model: Literal["zero", "fixed_per_order", "per_share", "bps"] = "per_share"
    usd_per_order: float = Field(default=0.0, ge=0.0)
    usd_per_share: float = Field(default=0.005, ge=0.0)
    minimum_usd_per_order: float = Field(default=0.0, ge=0.0)
    bps_of_notional: float = Field(default=0.0, ge=0.0)


class VolumeParticipationConfig(StrictModel):
    max_pct_of_bar_volume: float = Field(default=1.0, gt=0.0, le=100.0)
    on_exceed: Literal["reject", "resize"] = "reject"


class ExecutionConfig(StrictModel):
    spread: SpreadConfig = SpreadConfig()
    slippage: SlippageConfig = SlippageConfig()
    commission: CommissionConfig = CommissionConfig()
    volume_participation: VolumeParticipationConfig = VolumeParticipationConfig()
    cost_multiplier: float = Field(default=1.0, ge=0.0, le=100.0)


class RiskSizingConfig(StrictModel):
    model: Literal["risk_per_trade", "fixed_shares", "fixed_notional", "percent_equity"] = (
        "risk_per_trade"
    )
    risk_per_trade_pct_of_equity: float | None = Field(default=0.25, gt=0.0, le=100.0)
    fixed_shares: int | None = Field(default=None, gt=0)
    fixed_notional_usd: float | None = Field(default=None, gt=0.0)
    percent_of_equity: float | None = Field(default=None, gt=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_model_value(self) -> Self:
        required = {
            "risk_per_trade": self.risk_per_trade_pct_of_equity,
            "fixed_shares": self.fixed_shares,
            "fixed_notional": self.fixed_notional_usd,
            "percent_equity": self.percent_of_equity,
        }[self.model]
        if required is None:
            raise ValueError(f"sizing model {self.model} requires its matching value")
        return self


class RiskConfig(StrictModel):
    direction: Literal["long", "short", "both"] = "both"
    sizing: RiskSizingConfig = RiskSizingConfig()
    max_position_pct_of_equity: float = Field(default=25.0, gt=0.0, le=1000.0)
    max_gross_exposure_pct: float = Field(default=100.0, gt=0.0, le=1000.0)
    max_concurrent_positions: int = Field(default=3, gt=0)
    max_trades_per_session: int = Field(default=4, gt=0)
    max_daily_loss_pct_of_starting_equity: float = Field(default=1.0, gt=0.0, le=100.0)
    max_consecutive_losses: int = Field(default=3, gt=0)
    entry_start_time: time = time(9, 45)
    latest_entry_time: time = time(14, 30)
    cooldown_bars_after_exit: int = Field(default=1, ge=0)

    @field_validator("entry_start_time", "latest_entry_time", mode="before")
    @classmethod
    def parse_time(cls, value: Any) -> Any:
        if isinstance(value, str):
            return time.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_time_window(self) -> Self:
        if self.entry_start_time > self.latest_entry_time:
            raise ValueError("entry_start_time must not be after latest_entry_time")
        return self


class StrategyConfig(StrictModel):
    name: str
    expected_version: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("strategy name must be lowercase snake_case")
        return normalized


class ReportConfig(StrictModel):
    output_dir: Path = Path("runs")
    html: bool = True
    write_csv_copies: bool = False
    include_trade_feature_snapshots: bool = True
    include_mae_mfe: bool = True
    bootstrap_samples: int = Field(default=1000, ge=0, le=1_000_000)
    conclusion_gates_enabled: bool = True


class ResolutionMetadata(StrictModel):
    resolved_at_utc: datetime
    config_path: Path | None = None
    override_sources: tuple[str, ...] = ()


class ResolvedConfig(StrictModel):
    config_version: Literal["1.0"] = "1.0"
    project: ProjectConfig
    market: MarketConfig
    data: DataConfig
    engine: EngineConfig
    execution: ExecutionConfig
    risk: RiskConfig
    strategy: StrategyConfig
    report: ReportConfig
    resolution: ResolutionMetadata | None = None


class SplitConfig(StrictModel):
    method: Literal["chronological_sessions"] = "chronological_sessions"
    train_pct: float = Field(default=60.0, gt=0.0, lt=100.0)
    validation_pct: float = Field(default=20.0, ge=0.0, lt=100.0)
    test_pct: float = Field(default=20.0, gt=0.0, lt=100.0)
    embargo_sessions: int = Field(default=1, ge=0)
    final_test_immutable: bool = True

    @model_validator(mode="after")
    def validate_percentages(self) -> Self:
        total = self.train_pct + self.validation_pct + self.test_pct
        if abs(total - 100.0) > 1e-9:
            raise ValueError("train/validation/test percentages must sum to 100")
        return self


class SelectionConstraints(StrictModel):
    minimum_validation_trades: int = Field(default=30, ge=0)
    maximum_validation_drawdown_pct: float = Field(default=10.0, ge=0.0)
    minimum_validation_profit_factor: float = Field(default=1.0, ge=0.0)


class SelectionConfig(StrictModel):
    primary_metric: str
    tie_breakers: tuple[str, ...] = ()
    constraints: SelectionConstraints = SelectionConstraints()


class WalkForwardConfig(StrictModel):
    enabled: bool = True
    method: Literal["rolling", "anchored"] = "rolling"
    train_sessions: int = Field(default=120, gt=0)
    validation_sessions: int = Field(default=20, ge=0)
    test_sessions: int = Field(default=20, gt=0)
    step_sessions: int = Field(default=20, gt=0)


class StressConfig(StrictModel):
    cost_multipliers: tuple[float, ...] = (1.0, 2.0, 3.0)
    additional_entry_delay_bars: tuple[int, ...] = (0, 1)
    remove_best_trade: bool = True
    remove_best_session: bool = True
    parameter_neighborhood: bool = True
    bootstrap_sessions: int = Field(default=2000, ge=0)


class GateConfig(StrictModel):
    minimum_oos_trades: int = Field(default=100, ge=0)
    maximum_single_trade_profit_contribution_pct: float = Field(default=20.0, ge=0.0)
    maximum_single_session_profit_contribution_pct: float = Field(default=30.0, ge=0.0)
    require_nonnegative_at_2x_cost: bool = True
    require_parameter_plateau: bool = True


class ResearchBodyConfig(StrictModel):
    name: str
    base_config: Path
    random_seed: int = 42
    mode: Literal["grid", "random"] = "grid"
    max_trials: int = Field(default=200, gt=0)
    split: SplitConfig = SplitConfig()
    selection: SelectionConfig
    parameter_grid: dict[str, tuple[Any, ...]]
    walk_forward: WalkForwardConfig = WalkForwardConfig()
    stress: StressConfig = StressConfig()
    gates: GateConfig = GateConfig()


class ResearchConfig(StrictModel):
    config_version: Literal["1.0"] = "1.0"
    research: ResearchBodyConfig
