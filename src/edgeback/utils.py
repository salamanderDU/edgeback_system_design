import logging
import sys

# Default logging format for local CLI runs. Full details can go to runs later.
CLI_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class EdgeBackError(Exception):
    """Base exception for all EdgeBack application errors."""

    pass


class ConfigurationError(EdgeBackError):
    """Raised when configuration validation or loading fails."""

    pass


class DataError(EdgeBackError):
    """Raised for missing, malformed, or ambiguous market data."""

    pass


class SecretError(EdgeBackError):
    """Raised when secrets are inappropriately accessed or logged."""

    pass


def configure_logging(level: int = logging.INFO, verbose: bool = False) -> None:
    """
    Configures minimal logging. In the future, this can configure JSON logging for
    run artifacts, but for the MVP CLI, standard out is acceptable.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    logging.basicConfig(
        level=logging.DEBUG if verbose else level,
        format=CLI_LOG_FORMAT,
        handlers=handlers,
    )
