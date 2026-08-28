from pathlib import Path
from unittest.mock import patch

from edgeback.artifacts.reproducibility import compute_config_hash, get_git_metadata, initialize_run
from edgeback.config.loader import resolve_config


def test_stable_config_hash() -> None:
    config1 = resolve_config("configs/example_backtest.yaml")

    # modify a non-breaking UI thing
    config2 = resolve_config(
        yaml_path="configs/example_backtest.yaml",
        cli_overrides=["report.html=false", "report.bootstrap_samples=0"],
    )

    # The output report format doesn't affect execution logic hashing.
    assert compute_config_hash(config1) == compute_config_hash(config2)

    # modify a breaking thing
    config3 = resolve_config(
        yaml_path="configs/example_backtest.yaml", cli_overrides=["risk.max_trades_per_session=1"]
    )
    assert compute_config_hash(config1) != compute_config_hash(config3)


def test_initialize_run() -> None:
    config = resolve_config("configs/example_backtest.yaml")
    with patch(
        "edgeback.artifacts.reproducibility.get_git_metadata", return_value=("abcdef", False)
    ):
        run_metadata = initialize_run(config, strategy_version="1.0.0")

        assert run_metadata.status == "CREATED"
        assert run_metadata.git_commit == "abcdef"
        assert run_metadata.git_dirty is False
        assert run_metadata.random_seed == 42
        assert run_metadata.strategy.id == "opening_range_breakout"


def test_get_git_metadata_no_git() -> None:
    # If run in a bad directory
    commit, dirty = get_git_metadata(cwd=Path("/tmp/fake_dir_that_does_not_exist_xyz"))
    assert commit is None
    assert dirty is None
