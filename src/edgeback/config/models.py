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
    same_bar_bracket_policy: Literal[
        "stop_first", "target_first", "nearest_to_open", "reject_ambiguous_bar"
    ] = "stop_first"
    force_flat_at_session_end: bool = True
    entry_allocation: str = "priority_then_symbol"
    fractional_shares: bool = False
    max_leverage: float = Field(default=1.0, gt=0.0)


class SpreadConfig(BaseStrictModel):
    model: Literal["fixed_bps"] = "fixed_bps"
    full_spread_bps: float = Field(ge=0.0)


class SlippageConfig(BaseStrictModel):
    model: Literal["fixed_bps"] = "fixed_bps"
    bps_per_side: float = Field(ge=0.0)


class CommissionConfig(BaseStrictModel):
    """
    Commission model selection (docs/04 §6).

    Models:
    - ``zero`` — no commission.
    - ``fixed_per_order`` — requires ``usd_per_order``.
    - ``per_share`` — requires ``usd_per_share``, optional ``minimum_usd_per_order``.
    - ``bps`` — requires ``bps_of_notional``.
    """

    model: Literal["zero", "fixed_per_order", "per_share", "bps"] = "zero"
    usd_per_order: float | None = Field(default=None, ge=0.0)
    usd_per_share: float | None = Field(default=None, ge=0.0)
    minimum_usd_per_order: float | None = Field(default=None, ge=0.0)
    bps_of_notional: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_commission_params(self: "CommissionConfig") -> "CommissionConfig":
        if self.model == "fixed_per_order" and self.usd_per_order is None:
            raise ValueError("fixed_per_order commission requires usd_per_order")
        if self.model == "per_share" and self.usd_per_share is None:
            raise ValueError("per_share commission requires usd_per_share")
        if self.model == "bps" and self.bps_of_notional is None:
            raise ValueError("bps commission requires bps_of_notional")
        return self


class VolumeParticipationConfig(BaseStrictModel):
    max_pct_of_bar_volume: float = Field(gt=0.0, le=100.0)
    on_exceed: Literal["reject", "cap"] = "reject"


class ExecutionConfig(BaseStrictModel):
    spread: SpreadConfig
    slippage: SlippageConfig
    commission: CommissionConfig
    volume_participation: VolumeParticipationConfig


class RiskSizingConfig(BaseStrictModel):
    """
    Position-sizing model selection (docs/04 §8, FR-007).

    Models:
    - ``risk_per_trade`` — requires ``risk_per_trade_pct_of_equity``.
    - ``fixed_shares`` — requires ``fixed_shares``.
    - ``fixed_notional`` — requires ``fixed_notional_usd``.
    - ``percent_equity`` — requires ``percent_equity_pct``.
    """

    model: Literal["risk_per_trade", "fixed_shares", "fixed_notional", "percent_equity"] = (
        "risk_per_trade"
    )
    risk_per_trade_pct_of_equity: float | None = Field(default=None, gt=0.0, le=100.0)
    fixed_shares: int | None = Field(default=None, gt=0)
    fixed_notional_usd: float | None = Field(default=None, gt=0.0)
    percent_equity_pct: float | None = Field(default=None, gt=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_sizing_params(self: "RiskSizingConfig") -> "RiskSizingConfig":
        if self.model == "risk_per_trade" and self.risk_per_trade_pct_of_equity is None:
            raise ValueError("risk_per_trade sizing requires risk_per_trade_pct_of_equity")
        if self.model == "fixed_shares" and self.fixed_shares is None:
            raise ValueError("fixed_shares sizing requires fixed_shares")
        if self.model == "fixed_notional" and self.fixed_notional_usd is None:
            raise ValueError("fixed_notional sizing requires fixed_notional_usd")
        if self.model == "percent_equity" and self.percent_equity_pct is None:
            raise ValueError("percent_equity sizing requires percent_equity_pct")
        return self


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
