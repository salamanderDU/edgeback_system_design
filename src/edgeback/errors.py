"""Typed application errors and stable CLI exit codes."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIGURATION_ERROR = 2
    DATA_UNAVAILABLE = 3
    DATA_VALIDATION_FAILED = 4
    STRATEGY_ERROR = 5
    SIMULATION_FAILED = 6
    ARTIFACT_ERROR = 7
    RESEARCH_GATE_FAILED = 8


class EdgeBackError(Exception):
    """Base class carrying a stable exit code."""

    exit_code: ExitCode = ExitCode.SIMULATION_FAILED


class ConfigurationError(EdgeBackError):
    exit_code = ExitCode.CONFIGURATION_ERROR


class DataUnavailableError(EdgeBackError):
    exit_code = ExitCode.DATA_UNAVAILABLE


class DataValidationError(EdgeBackError):
    exit_code = ExitCode.DATA_VALIDATION_FAILED


class StrategyError(EdgeBackError):
    exit_code = ExitCode.STRATEGY_ERROR


class SimulationError(EdgeBackError):
    exit_code = ExitCode.SIMULATION_FAILED


class ArtifactError(EdgeBackError):
    exit_code = ExitCode.ARTIFACT_ERROR


class ResearchGateError(EdgeBackError):
    exit_code = ExitCode.RESEARCH_GATE_FAILED
