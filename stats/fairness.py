"""Tier 1 fairness analyses: chi-square, multiple-comparisons correction, Monte Carlo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


@dataclass
class ChiSquareResult:
    stat: float
    dof: int
    p_value: float
    observed: pd.Series  # indexed 1..n_categories
    expected: float
    fig: Figure


def chi_square_uniformity(samples: pd.Series, n_categories: int) -> ChiSquareResult:
    """Goodness-of-fit χ² for samples against discrete uniform over [1, n_categories]."""
    counts = samples.value_counts().reindex(range(1, n_categories + 1), fill_value=0)
    n = int(counts.sum())
    expected = n / n_categories
    stat, p = stats.chisquare(f_obs=counts.values, f_exp=[expected] * n_categories)
    dof = n_categories - 1

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(counts.index, counts.values, color="steelblue", alpha=0.7)
    ax.axhline(expected, color="red", linestyle="--", label=f"expected={expected:.1f}")
    ax.set_xlabel("ball")
    ax.set_ylabel("observed count")
    ax.set_title(f"χ²={stat:.2f}, dof={dof}, p={p:.4f}")
    ax.legend()
    fig.tight_layout()

    return ChiSquareResult(
        stat=float(stat), dof=dof, p_value=float(p),
        observed=counts, expected=expected, fig=fig,
    )


def correct_pvalues(
    pvals: pd.Series,
    *,
    method: Literal["bonferroni", "fdr_bh"],
) -> pd.DataFrame:
    """Apply multiple-comparisons correction and return raw vs corrected p-values."""
    from statsmodels.stats.multitest import multipletests

    reject, corrected, _, _ = multipletests(pvals.values, alpha=0.05, method=method)
    return pd.DataFrame({
        "pval_raw": pvals.values,
        "pval_corrected": corrected,
        "significant_at_05": reject,
    }, index=pvals.index)


def simulate_null(
    *,
    range_: int,
    n_balls: int,
    n_draws: int,
    n_sim: int,
    statistic_fn: Callable[[np.ndarray], float],
    seed: int,
) -> np.ndarray:
    """Simulate `n_sim` fair lotteries, apply `statistic_fn`, return empirical null.

    `statistic_fn` receives a flat 1-D array of length n_draws*n_balls
    (the "long" form, one ball per element).
    """
    rng = np.random.default_rng(seed)
    out = np.empty(n_sim, dtype=float)
    for i in range(n_sim):
        # draw n_balls without replacement per draw, n_draws times
        draws = np.empty((n_draws, n_balls), dtype=np.int32)
        for k in range(n_draws):
            draws[k] = rng.choice(range_, size=n_balls, replace=False) + 1
        out[i] = statistic_fn(draws.reshape(-1))
    return out
