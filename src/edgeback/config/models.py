from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BaseStrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProjectConfig(BaseStrictModel):
    name: str
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    random_seed: int = 42


class MarketConfig(BaseStrictModel):
    calendar: str = "XNYS"
    timezone: str = "America/New_York"
    session: str = "regular"
    include_extended_hours: bool = False


class DateRangeConfig(BaseStrictModel):
    mode: Literal["rolling", "exact"] = "rolling"
    lookback_calendar_days: int | None = None
    start: str | None = None
    end: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self: "DateRangeConfig") -> "DateRangeConfig":
        if self.mode == "rolling":
            if self.lookback_calendar_days is None:
                raise ValueError("rolling mode requires lookback_calendar_days")
        elif self.mode == "exact":
            if self.start is None:
                raise ValueError("exact mode requires start date")
        return self


class DataConfig(BaseStrictModel):
    provider: str
    feed: str
    symbols: list[str]
    interval: str
    date_range: DateRangeConfig
    adjustment_mode: str = "split_adjusted"
    cache_dir: str = "data"
    minimum_session_completeness_pct: float = Field(default=98.0, ge=0.0, le=100.0)
    missing_session_policy: Literal["fail_session", "ignore"] = "fail_session"
    allow_incomplete_latest_bar: bool = False


class EngineConfig(BaseStrictModel):
    initial_cash_usd: float = Field(gt=0.0)
    signal_time: Literal["bar_close"] = "bar_close"
    market_fill_timing: Literal["next_bar_open"] = "next_bar_open"
    same_bar_bracket_policy: Literal["stop_first", "target_first"] = "stop_first"
    force_flat_at_session_end: bool = True
    entry_allocation: str = "priority_then_symbol"
    fractional_shares: bool = False
    max_leverage: float = Field(default=1.0, gt=0.0)


class SpreadConfig(BaseStrictModel):
    model: str
    full_spread_bps: float = Field(ge=0.0)


class SlippageConfig(BaseStrictModel):
    model: str
    bps_per_side: float = Field(ge=0.0)


class CommissionConfig(BaseStrictModel):
    model: str
    usd_per_share: float = Field(ge=0.0)
    minimum_usd_per_order: float = Field(ge=0.0)


class VolumeParticipationConfig(BaseStrictModel):
    max_pct_of_bar_volume: float = Field(gt=0.0, le=100.0)
    on_exceed: Literal["reject", "cap"] = "reject"


class ExecutionConfig(BaseStrictModel):
    spread: SpreadConfig
    slippage: SlippageConfig
    commission: CommissionConfig
    volume_participation: VolumeParticipationConfig


class RiskSizingConfig(BaseStrictModel):
    model: str
    risk_per_trade_pct_of_equity: float | None = Field(default=None, gt=0.0, le=100.0)
    fixed_shares: int | None = Field(default=None, gt=0)


class RiskConfig(BaseStrictModel):
    direction: Literal["long", "short", "both"] = "both"
    sizing: RiskSizingConfig
    max_position_pct_of_equity: float = Field(gt=0.0, le=100.0)
    max_gross_exposure_pct: float = Field(gt=0.0)
    max_concurrent_positions: int = Field(gt=0)
    max_trades_per_session: int = Field(gt=0)
    max_daily_loss_pct_of_starting_equity: float = Field(gt=0.0, le=100.0)
    max_consecutive_losses: int = Field(gt=0)
    entry_start_time: str
    latest_entry_time: str
    cooldown_bars_after_exit: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_times(self: "RiskConfig") -> "RiskConfig":
        if self.entry_start_time > self.latest_entry_time:
            raise ValueError("entry_start_time cannot be after latest_entry_time")
        return self


class StrategyConfig(BaseStrictModel):
    name: str
    expected_version: str
    params: dict[str, Any] = Field(default_factory=dict)


class ReportConfig(BaseStrictModel):
    output_dir: str = "runs"
    html: bool = True
    write_csv_copies: bool = False
    include_trade_feature_snapshots: bool = True
    include_mae_mfe: bool = True
    bootstrap_samples: int = Field(default=1000, ge=0)
    conclusion_gates_enabled: bool = True


class BacktestConfig(BaseStrictModel):
    config_version: str = "1.0"
    project: ProjectConfig
    market: MarketConfig
    data: DataConfig
    engine: EngineConfig
    execution: ExecutionConfig
    risk: RiskConfig
    strategy: StrategyConfig
    report: ReportConfig
