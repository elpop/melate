"""F0.5 — derive jackpot_won / rollover flag from the BOLSA (award) series."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


class FloorEstimateWarning(UserWarning):
    """Raised when the minimum and the Q1-mode of award disagree."""


def estimate_floor(award: pd.Series, *, eps: float = 0.05) -> float:
    """Estimate the jackpot floor from the BOLSA series.

    Use the minimum, but warn if it disagrees with the mode of the lower quartile
    (sign of an outlier or anomalous data point).
    """
    candidate_min = float(award.min())
    q10 = award.quantile(0.10)
    lower = award[award <= q10]
    if lower.empty:
        return candidate_min
    mode_res = stats.mode(lower.values, keepdims=False)
    candidate_mode = float(mode_res.mode)
    if candidate_mode == 0:
        return candidate_min
    rel_diff = abs(candidate_min - candidate_mode) / candidate_mode
    if rel_diff > eps:
        warnings.warn(
            f"floor_estimate: min={candidate_min:.0f} and Q1-mode={candidate_mode:.0f} "
            f"disagree by {rel_diff:.1%}; using min (conservative)",
            FloorEstimateWarning,
        )
    return candidate_min
