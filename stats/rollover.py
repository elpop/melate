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

    Use the most recurrent value in the lower quartile (the floor that the
    lottery actually resets to on jackpot wins). The min is reported as a
    sanity check; if it disagrees with the mode significantly, raise a
    warning — this typically means there are missing-data outliers
    (award == 0) or the floor changed over the period.
    """
    # Strip clearly invalid values (the real Melate CSV has award=0 rows in
    # the early years where the prize was not recorded).
    valid = award[award > 0]
    if valid.empty:
        raise ValueError("all award values non-positive; cannot estimate floor")

    candidate_min = float(valid.min())
    q10 = valid.quantile(0.10)
    lower = valid[valid <= q10]
    mode_res = stats.mode(lower.values, keepdims=False)
    candidate_mode = float(mode_res.mode)
    rel_diff = (
        abs(candidate_min - candidate_mode) / candidate_mode
        if candidate_mode > 0 else 1.0
    )
    if rel_diff > eps:
        warnings.warn(
            f"floor_estimate: valid_min={candidate_min:.0f} and "
            f"Q1-mode={candidate_mode:.0f} disagree by {rel_diff:.1%}; "
            "using mode (most recurrent reset value)",
            FloorEstimateWarning,
        )
    return candidate_mode


def derive_jackpot_won(
    award: pd.Series,
    *,
    eps: float = 0.05,
    threshold: float = 1.2,
) -> pd.DataFrame:
    """Per-draw boolean: was the jackpot won at this draw (BOLSA resets next draw)?

    Rule: jackpot_won[k] := award[k+1] ≤ floor*(1+eps) AND award[k] ≥ floor*threshold.
    Last draw has no k+1 → NaN. Ambiguous = caída sin buildup, marcado para auditoría.
    """
    award = award.reset_index(drop=True)
    floor = estimate_floor(award, eps=eps)
    n = len(award)

    # `boolean` is pandas' nullable bool dtype — supports True/False/NA
    # without the lint noise of `== True` on object-dtype columns.
    jackpot = pd.Series([pd.NA] * n, dtype="boolean")
    ambiguous = pd.Series([False] * n, dtype="bool")

    for k in range(n - 1):
        curr_val = award.iloc[k]
        next_val = award.iloc[k + 1]
        # award == 0 in the real CSV means missing data (no prize recorded for
        # that draw), not a literal zero peso reset. Either value missing →
        # we cannot judge → mark ambiguous, do not count as a win.
        if curr_val == 0 or next_val == 0:
            jackpot.iloc[k] = False
            ambiguous.iloc[k] = True
            continue
        next_low = next_val <= floor * (1 + eps)
        curr_high = curr_val >= floor * threshold
        curr_low = curr_val <= floor * (1 + eps)
        if next_low and curr_high:
            jackpot.iloc[k] = True
        elif next_low and curr_low:
            # already at floor (post-reset, no buildup yet) → just not a win,
            # not ambiguous (this is the normal post-reset slack)
            jackpot.iloc[k] = False
        elif next_low and not curr_high:
            # mid-range buildup that drops back to floor → truly ambiguous
            jackpot.iloc[k] = False
            ambiguous.iloc[k] = True
        else:
            jackpot.iloc[k] = False

    return pd.DataFrame({
        "draw": range(1, n + 1),
        "award": award.values,
        "jackpot_won": jackpot.values,
        "ambiguous": ambiguous.values,
        "floor_estimate": [floor] * n,
    })
