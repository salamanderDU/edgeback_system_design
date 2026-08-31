"""Seeded session-level bootstrap uncertainty."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def session_bootstrap(
    trades: pd.DataFrame,
    *,
    samples: int,
    seed: int,
    confidence: float = 0.95,
) -> dict[str, Any]:
    if trades.empty or samples <= 0:
        return {"samples": 0, "reason": "no trades or bootstrap disabled"}
    grouped = [group["net_pnl_usd"].astype(float).to_numpy() for _, group in trades.groupby("session_date", sort=True)]
    if not grouped:
        return {"samples": 0, "reason": "no sessions"}
    rng = np.random.default_rng(seed)
    expectancy: list[float] = []
    total_pnl: list[float] = []
    for _ in range(samples):
        chosen = rng.integers(0, len(grouped), size=len(grouped))
        sample = np.concatenate([grouped[index] for index in chosen])
        expectancy.append(float(sample.mean()))
        total_pnl.append(float(sample.sum()))
    alpha = (1.0 - confidence) / 2.0
    return {
        "samples": samples,
        "seed": seed,
        "confidence": confidence,
        "expectancy_usd_per_trade_ci": [
            float(np.quantile(expectancy, alpha)),
            float(np.quantile(expectancy, 1.0 - alpha)),
        ],
        "net_pnl_usd_ci": [
            float(np.quantile(total_pnl, alpha)),
            float(np.quantile(total_pnl, 1.0 - alpha)),
        ],
    }
