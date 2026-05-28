"""Tarea 4 — walk-forward backtest of the `-weight` feature from melate.pl."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


def predict_weight_balls(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
) -> list[int]:
    """Reproduce melate.pl:786-800 weighting on the most-recent `window` draws.

    - Take the last `window` rows of draws_wide (sorted ascending by draw).
    - Split into segments of size `breaks`. Most-recent segment gets highest level.
    - Per ball: sum count_in_segment * level. Return top n_balls.
    """
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    recent = draws_wide.sort_values("draw").tail(window).reset_index(drop=True)
    # Newest first inside `recent` — split so segment 0 is newest.
    recent_rev = recent.iloc[::-1].reset_index(drop=True)
    n_segments = (len(recent_rev) + breaks - 1) // breaks
    weights = np.zeros(range_ + 1, dtype=float)
    for seg_idx in range(n_segments):
        level = n_segments - seg_idx
        seg = recent_rev.iloc[seg_idx * breaks:(seg_idx + 1) * breaks]
        balls = seg[ball_cols].to_numpy().reshape(-1)
        for b in balls:
            weights[int(b)] += level
    # Top n_balls by weight, break ties by lower number (deterministic).
    ranked = sorted(range(1, range_ + 1),
                    key=lambda b: (-weights[b], b))
    return ranked[:n_balls]


class DataLeakageError(RuntimeError):
    """Raised when the history slice would contain a draw at or beyond
    the evaluation index — i.e. the input is duplicated or out of order."""


def walk_forward_hits(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
    start_at: int = 2,
) -> list[int]:
    """For each draw k starting at `start_at`, predict using draws[:k] and count hits vs draws[k]."""
    ordered = draws_wide.sort_values("draw").reset_index(drop=True)
    hits = []
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    for k in range(start_at, len(ordered) + 1):
        history = ordered.iloc[: k - 1]
        target_row = ordered.iloc[k - 1]
        # Anti-leakage: history must be strictly before target.
        if (history["draw"] >= target_row["draw"]).any():
            raise DataLeakageError(
                f"history contains draw >= target {target_row['draw']}; "
                "input may have duplicates or be out of order"
            )
        picks = predict_weight_balls(
            history, n_balls=n_balls, range_=range_,
            window=window, breaks=breaks,
        )
        actual = set(int(target_row[c]) for c in ball_cols)
        hits.append(len(actual & set(picks)))
    return hits
