"""Chronological exchange-session splits and walk-forward folds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from edgeback.config.models import SplitConfig, WalkForwardConfig
from edgeback.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SessionSplit:
    train: tuple[date, ...]
    validation: tuple[date, ...]
    test: tuple[date, ...]
    embargo_train_validation: tuple[date, ...]
    embargo_validation_test: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_id: str
    train: tuple[date, ...]
    validation: tuple[date, ...]
    test: tuple[date, ...]


def chronological_session_split(sessions: list[date] | tuple[date, ...], config: SplitConfig) -> SessionSplit:
    ordered = tuple(sorted(set(sessions)))
    usable_count = len(ordered) - 2 * config.embargo_sessions
    if usable_count < 3:
        raise ConfigurationError("Not enough sessions for train/validation/test plus embargo")
    train_count = max(1, int(usable_count * config.train_pct / 100.0))
    validation_count = max(1, int(usable_count * config.validation_pct / 100.0))
    test_count = usable_count - train_count - validation_count
    if test_count < 1:
        validation_count = max(1, validation_count - (1 - test_count))
        test_count = usable_count - train_count - validation_count
    if test_count < 1:
        raise ConfigurationError("Split percentages leave no final-test sessions")
    cursor = 0
    train = ordered[cursor : cursor + train_count]
    cursor += train_count
    embargo_one = ordered[cursor : cursor + config.embargo_sessions]
    cursor += config.embargo_sessions
    validation = ordered[cursor : cursor + validation_count]
    cursor += validation_count
    embargo_two = ordered[cursor : cursor + config.embargo_sessions]
    cursor += config.embargo_sessions
    test = ordered[cursor:]
    return SessionSplit(train, validation, test, embargo_one, embargo_two)


def walk_forward_folds(
    sessions: list[date] | tuple[date, ...], config: WalkForwardConfig
) -> tuple[WalkForwardFold, ...]:
    ordered = tuple(sorted(set(sessions)))
    folds: list[WalkForwardFold] = []
    train_start = 0
    train_end = config.train_sessions
    fold_number = 1
    while True:
        validation_end = train_end + config.validation_sessions
        test_end = validation_end + config.test_sessions
        if test_end > len(ordered):
            break
        train = ordered[train_start:train_end]
        validation = ordered[train_end:validation_end]
        test = ordered[validation_end:test_end]
        folds.append(
            WalkForwardFold(
                fold_id=f"fold-{fold_number:03d}",
                train=train,
                validation=validation,
                test=test,
            )
        )
        fold_number += 1
        train_end += config.step_sessions
        if config.method == "rolling":
            train_start += config.step_sessions
    return tuple(folds)
