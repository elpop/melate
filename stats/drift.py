"""Tarea 10 — temporal drift / change-point detection per ball.

Each ball's appearance series is Bernoulli(p=n_balls/range_) under fair
independent draws. A change-point test detects whether p shifts at some
point in the series — useful when a balota wears out or is replaced.
We use Pettitt's test (non-parametric, rank-based, single change-point)
applied to each ball's 0/1 indicator series, with Bonferroni correction
over the `range_` balls.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from matplotlib.figure import Figure


@dataclass
class DriftResult:
    n_draws: int
    per_ball: pd.DataFrame      # ball, stat, p_value, change_point_index, significant_at_bonferroni
    n_significant_at_nominal_05: int
    n_significant_at_bonferroni: int
    bonferroni_threshold: float
    fig: Figure


def pettitt_test(x) -> tuple[float, float, int]:
    """Pettitt's non-parametric test for a single change-point.

    Statistic K = max_k |U_k| where
        U_k = sum_{i<=k} sum_{j>k} sign(x_i - x_j)
    For binary x (0/1) this is closed-form via cumulative counts.

    Returns (K, p_value, change_point_index). The change point is the
    1-indexed position where the shift is most likely to have occurred
    (i.e., the argmax of |U_k|).

    p-value uses the asymptotic approximation
        p ≈ 2 · exp(−6 · K² / (n³ + n²))
    capped at 1.
    """
    x = np.asarray(x, dtype=np.int64)
    n = len(x)
    if n < 4:
        return 0.0, 1.0, 0
    s = np.cumsum(x)
    S = int(s[-1])
    ks = np.arange(1, n, dtype=np.int64)            # k = 1, …, n−1
    s_k = s[:-1].astype(np.int64)
    ones_left = s_k
    zeros_left = ks - s_k
    ones_right = S - s_k
    zeros_right = (n - ks) - ones_right
    U = ones_left * zeros_right - zeros_left * ones_right
    abs_U = np.abs(U)
    K = float(abs_U.max())
    cp = int(np.argmax(abs_U)) + 1                  # 1-indexed change point
    p_value = float(min(2.0 * np.exp(-6.0 * K * K / (n ** 3 + n * n)), 1.0))
    return K, p_value, cp


def _rolling_appearance_rate(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling mean of x with window size; aligned to the right (last)."""
    if window > len(x):
        return np.full(len(x), x.mean())
    csum = np.concatenate([[0], np.cumsum(x)])
    out = (csum[window:] - csum[:-window]) / window
    pad = np.full(window - 1, x.mean())
    return np.concatenate([pad, out])


def pettitt_per_ball(
    draws_wide: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    alpha: float = 0.05,
) -> DriftResult:
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    ordered = draws_wide.sort_values("draw").reset_index(drop=True)
    n_draws = len(ordered)

    rows = []
    most_extreme_ball = None
    most_extreme_p = 1.0
    for ball in range(1, range_ + 1):
        appears = (ordered[ball_cols] == ball).any(axis=1).to_numpy().astype(int)
        K, p, cp = pettitt_test(appears)
        rows.append({
            "ball": ball,
            "stat": K,
            "p_value": p,
            "change_point_index": cp,
        })
        if p < most_extreme_p:
            most_extreme_p = p
            most_extreme_ball = ball

    per_ball = pd.DataFrame(rows)
    bonf_threshold = alpha / range_
    per_ball["significant_at_bonferroni"] = per_ball["p_value"] < bonf_threshold
    n_nominal = int((per_ball["p_value"] < alpha).sum())
    n_bonf = int(per_ball["significant_at_bonferroni"].sum())

    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    # Left: per-ball p-values (log scale).
    axes[0].scatter(
        per_ball["ball"], per_ball["p_value"],
        c=np.where(per_ball["significant_at_bonferroni"], "red", "steelblue"),
        alpha=0.7,
    )
    axes[0].axhline(alpha, color="orange", linestyle=":", label=f"nominal α={alpha}")
    axes[0].axhline(bonf_threshold, color="red", linestyle="--",
                    label=f"Bonferroni α/range={bonf_threshold:.4f}")
    axes[0].set_xlabel("ball")
    axes[0].set_ylabel("Pettitt p-value")
    axes[0].set_yscale("log")
    axes[0].set_title(
        f"Pettitt p-value per ball  (Bonferroni-significant: {n_bonf}/{range_})"
    )
    axes[0].legend()

    # Right: rolling appearance rate for the most-extreme ball (purely diagnostic).
    if most_extreme_ball is not None:
        appears = (ordered[ball_cols] == most_extreme_ball).any(axis=1).to_numpy().astype(int)
        window = max(50, n_draws // 20)
        roll = _rolling_appearance_rate(appears, window)
        axes[1].plot(roll, color="steelblue",
                     label=f"ball {most_extreme_ball} rolling mean ({window}-draw)")
        axes[1].axhline(n_balls / range_, color="red", linestyle="--",
                        label=f"theoretical p={n_balls/range_:.4f}")
        cp = int(per_ball.loc[per_ball["ball"] == most_extreme_ball,
                              "change_point_index"].iloc[0])
        axes[1].axvline(cp, color="gray", linestyle=":",
                        label=f"Pettitt change-point @ draw {cp}")
        axes[1].set_xlabel("draw index")
        axes[1].set_ylabel("appearance rate")
        axes[1].set_title(
            f"Most-extreme ball {most_extreme_ball}: p={most_extreme_p:.4f}"
        )
        axes[1].legend()
    fig.tight_layout()

    return DriftResult(
        n_draws=n_draws,
        per_ball=per_ball,
        n_significant_at_nominal_05=n_nominal,
        n_significant_at_bonferroni=n_bonf,
        bonferroni_threshold=bonf_threshold,
        fig=fig,
    )
