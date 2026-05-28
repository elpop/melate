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


@dataclass
class BacktestResult:
    hit_rate_weight: float
    hit_rate_baseline_analytical: float
    baseline_ci_95: tuple[float, float]
    p_value_vs_baseline: float
    hits_per_draw_series: pd.Series
    fig: Figure


def _hypergeom_mean_var(range_: int, n_balls: int) -> tuple[float, float]:
    """E[hits] and Var[hits] for hits = |picks ∩ actual| under uniform picks."""
    # hits ~ Hypergeometric(N=range_, K=n_balls, n=n_balls)
    N, K, n = range_, n_balls, n_balls
    mean = n * K / N
    var = n * K * (N - K) * (N - n) / (N ** 2 * (N - 1))
    return mean, var


def weight_walkforward(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
    start_at: int = 2,
) -> BacktestResult:
    hits = walk_forward_hits(
        draws_wide, n_balls=n_balls, range_=range_,
        window=window, breaks=breaks, start_at=start_at,
    )
    hits_arr = np.array(hits, dtype=float)
    n_evals = len(hits_arr)
    # All "hit_rate_*" fields are mean hits PER DRAW (out of n_balls picks),
    # following the design doc convention E[hits] = n_balls²/range_.
    hit_rate_weight = float(hits_arr.mean())

    mean_h, var_h = _hypergeom_mean_var(range_, n_balls)
    se_mean = (var_h / n_evals) ** 0.5
    ci_lo = mean_h - 1.96 * se_mean
    ci_hi = mean_h + 1.96 * se_mean

    # Compare observed mean hits to expected mean via a z-test on the mean.
    z = (hits_arr.mean() - mean_h) / se_mean if se_mean > 0 else 0.0
    p = float(2 * (1 - stats.norm.cdf(abs(z))))

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hits_arr, color="steelblue", alpha=0.5, label="hits / draw")
    ax.axhline(mean_h, color="red", linestyle="--",
               label=f"baseline mean={mean_h:.2f}")
    ax.axhline(mean_h + 1.96 * (var_h ** 0.5), color="red", linestyle=":",
               alpha=0.3, label="±1.96·σ (per-draw)")
    ax.axhline(mean_h - 1.96 * (var_h ** 0.5), color="red", linestyle=":",
               alpha=0.3)
    ax.set_xlabel("evaluation index (k - start_at)")
    ax.set_ylabel("hits per draw")
    ax.set_title(
        f"weight_mean_hits={hit_rate_weight:.3f}, "
        f"baseline_mean_hits={mean_h:.3f}, p={p:.4f}"
    )
    ax.legend()
    fig.tight_layout()

    return BacktestResult(
        hit_rate_weight=hit_rate_weight,
        hit_rate_baseline_analytical=mean_h,
        baseline_ci_95=(ci_lo, ci_hi),
        p_value_vs_baseline=p,
        hits_per_draw_series=pd.Series(hits_arr, name="hits"),
        fig=fig,
    )
