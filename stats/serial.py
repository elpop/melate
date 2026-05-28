"""Tarea 9 — runs / autocorrelación serial per ball.

Two independence diagnostics applied to each ball's 0/1 appearance series:

  - **Wald-Wolfowitz runs test**: a "run" is a maximal stretch of equal
    values. Under independence, the number of runs is approximately
    normal with closed-form mean and variance.
  - **Lag-1 autocorrelation**: ρ̂_1 is approximately N(0, 1/n) under
    independence.

The per-ball decision combines the two via the minimum p-value;
Bonferroni correction is then applied over the `range_` balls.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy.stats import norm


@dataclass
class SerialResult:
    n_draws: int
    per_ball: pd.DataFrame      # ball, n_runs, expected_runs, z_runs, p_runs, lag1_autocorr, p_lag1, min_p, significant_at_bonferroni
    n_significant_at_nominal_05: int
    n_significant_at_bonferroni: int
    bonferroni_threshold: float
    fig: Figure


def runs_test(x) -> tuple[int, float, float, float]:
    """Wald-Wolfowitz runs test on a binary 0/1 sequence.

    Returns (n_runs, expected_runs, z, p_value). Two-sided p-value
    against the normal approximation, valid for n_1, n_0 ≥ 10.
    """
    x = np.asarray(x, dtype=np.int64)
    n = len(x)
    n1 = int(x.sum())
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return 1, 1.0, 0.0, 1.0
    # Number of runs = 1 + count of transitions.
    n_runs = int(1 + np.sum(np.diff(x) != 0))
    expected = 2.0 * n1 * n0 / n + 1.0
    var = 2.0 * n1 * n0 * (2.0 * n1 * n0 - n) / (n * n * (n - 1)) if n > 1 else 0.0
    if var <= 0:
        return n_runs, expected, 0.0, 1.0
    z = (n_runs - expected) / np.sqrt(var)
    p = float(2.0 * (1.0 - norm.cdf(abs(z))))
    return n_runs, float(expected), float(z), p


def lag1_autocorrelation(x) -> tuple[float, float]:
    """Lag-1 autocorrelation and its two-sided p-value under H0: ρ_1 = 0.

    Under independence, ρ̂_1 ~ N(0, 1/n) asymptotically.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    mean = x.mean()
    var = x.var()
    if var == 0:
        return 0.0, 1.0
    cov1 = np.mean((x[:-1] - mean) * (x[1:] - mean))
    rho = float(cov1 / var)
    se = 1.0 / np.sqrt(n)
    z = rho / se
    p = float(2.0 * (1.0 - norm.cdf(abs(z))))
    return rho, p


def serial_independence_per_ball(
    draws_wide: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    alpha: float = 0.05,
) -> SerialResult:
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    ordered = draws_wide.sort_values("draw").reset_index(drop=True)
    n_draws = len(ordered)

    rows = []
    for ball in range(1, range_ + 1):
        appears = (ordered[ball_cols] == ball).any(axis=1).to_numpy().astype(int)
        n_runs, expected_runs, z_runs, p_runs = runs_test(appears)
        rho, p_lag1 = lag1_autocorrelation(appears)
        min_p = min(p_runs, p_lag1)
        rows.append({
            "ball": ball,
            "n_runs": n_runs,
            "expected_runs": expected_runs,
            "z_runs": z_runs,
            "p_runs": p_runs,
            "lag1_autocorr": rho,
            "p_lag1": p_lag1,
            "min_p": min_p,
        })

    per_ball = pd.DataFrame(rows)
    # Bonferroni over balls × 2 tests per ball.
    bonf_threshold = alpha / (range_ * 2)
    per_ball["significant_at_bonferroni"] = per_ball["min_p"] < bonf_threshold
    n_nominal = int((per_ball["min_p"] < alpha).sum())
    n_bonf = int(per_ball["significant_at_bonferroni"].sum())

    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    # Left: runs-test z per ball with ±1.96 band.
    axes[0].scatter(per_ball["ball"], per_ball["z_runs"],
                    color="steelblue", alpha=0.7)
    axes[0].axhline(1.96, color="orange", linestyle=":", label="±1.96 (nominal)")
    axes[0].axhline(-1.96, color="orange", linestyle=":")
    axes[0].axhline(0, color="gray", linestyle="-", linewidth=0.5)
    bonf_z = float(norm.ppf(1 - bonf_threshold / 2))
    axes[0].axhline(bonf_z, color="red", linestyle="--",
                    label=f"±{bonf_z:.2f} (Bonferroni)")
    axes[0].axhline(-bonf_z, color="red", linestyle="--")
    axes[0].set_xlabel("ball")
    axes[0].set_ylabel("Wald-Wolfowitz runs z")
    axes[0].set_title("Runs test z per ball")
    axes[0].legend()

    # Right: lag-1 autocorrelation per ball with ±1.96/√n band.
    ci_half = 1.96 / np.sqrt(n_draws)
    axes[1].scatter(per_ball["ball"], per_ball["lag1_autocorr"],
                    color="steelblue", alpha=0.7)
    axes[1].axhline(ci_half, color="orange", linestyle=":",
                    label=f"±{ci_half:.3f} (nominal 95%)")
    axes[1].axhline(-ci_half, color="orange", linestyle=":")
    axes[1].axhline(0, color="gray", linestyle="-", linewidth=0.5)
    axes[1].set_xlabel("ball")
    axes[1].set_ylabel("lag-1 autocorrelation")
    axes[1].set_title(f"Lag-1 autocorrelation per ball (n={n_draws})")
    axes[1].legend()
    fig.tight_layout()

    return SerialResult(
        n_draws=n_draws,
        per_ball=per_ball,
        n_significant_at_nominal_05=n_nominal,
        n_significant_at_bonferroni=n_bonf,
        bonferroni_threshold=bonf_threshold,
        fig=fig,
    )
