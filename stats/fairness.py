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
