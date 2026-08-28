import importlib

import edgeback


def test_package_import() -> None:
    """Verify that the package can be imported."""
    assert edgeback.__name__ == "edgeback"


def test_cli_import() -> None:
    """Verify that the CLI module can be imported."""
    cli = importlib.import_module("edgeback.cli")
    assert cli is not None
