import pytest
from pydantic import ValidationError

from edgeback.config.models import (
    DateRangeConfig,
    RiskConfig,
    RiskSizingConfig,
)


def test_config_frozen() -> None:
    config = DateRangeConfig(mode="rolling", lookback_calendar_days=50)
    with pytest.raises(ValidationError):
        config.lookback_calendar_days = 60  # type: ignore


def test_config_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        DateRangeConfig(mode="rolling", lookback_calendar_days=50, random_extra_key="bad")  # type: ignore


def test_date_range_validation() -> None:
    # Valid rolling
    DateRangeConfig(mode="rolling", lookback_calendar_days=30)

    # Invalid rolling
    with pytest.raises(ValidationError, match="rolling mode requires lookback_calendar_days"):
        DateRangeConfig(mode="rolling")

    # Valid exact
    DateRangeConfig(mode="exact", start="2024-01-01")

    # Invalid exact
    with pytest.raises(ValidationError, match="exact mode requires start date"):
        DateRangeConfig(mode="exact")


def test_risk_config_validation() -> None:
    # Valid
    RiskConfig(
        direction="both",
        sizing=RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=1.0),
        max_position_pct_of_equity=25.0,
        max_gross_exposure_pct=100.0,
        max_concurrent_positions=3,
        max_trades_per_session=4,
        max_daily_loss_pct_of_starting_equity=1.0,
        max_consecutive_losses=3,
        entry_start_time="09:30",
        latest_entry_time="15:30",
        cooldown_bars_after_exit=1,
    )

    # Invalid times
    with pytest.raises(ValidationError, match="entry_start_time cannot be after latest_entry_time"):
        RiskConfig(
            direction="both",
            sizing=RiskSizingConfig(model="risk_per_trade", risk_per_trade_pct_of_equity=1.0),
            max_position_pct_of_equity=25.0,
            max_gross_exposure_pct=100.0,
            max_concurrent_positions=3,
            max_trades_per_session=4,
            max_daily_loss_pct_of_starting_equity=1.0,
            max_consecutive_losses=3,
            entry_start_time="15:30",
            latest_entry_time="09:30",
            cooldown_bars_after_exit=1,
        )
