"""Tarea 5 — conscious-selection lower bound via rollover excess."""
from __future__ import annotations

from dataclasses import dataclass
from math import comb

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


@dataclass
class RolloverExcessResult:
    observed_rollover_rate: float
    per_N: pd.DataFrame  # N, expected_rate_poisson, ratio, p_value, ci_lo, ci_hi
    fig: Figure


def rollover_excess(
    jackpot_df: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    n_players_grid,
) -> RolloverExcessResult:
    """Compare observed rollover rate against Poisson-uniform predictions for a grid of N."""
    won = jackpot_df["jackpot_won"].dropna()
    # rollover ⇔ NOT won
    rollovers = (won == False).sum()
    n_obs = len(won)
    observed_rate = rollovers / n_obs

    p_jackpot = 1.0 / comb(range_, n_balls)

    rows = []
    for N in n_players_grid:
        expected_rate = float(np.exp(-N * p_jackpot))
        ratio = observed_rate / expected_rate if expected_rate > 0 else float("inf")
        # Binomial test: observed rollovers ~ Binomial(n_obs, expected_rate)
        binom = stats.binomtest(rollovers, n_obs, expected_rate, alternative="two-sided")
        p_value = binom.pvalue
        ci_lo, ci_hi = binom.proportion_ci(confidence_level=0.95)
        rows.append({
            "N": int(N),
            "expected_rate_poisson": expected_rate,
            "ratio": ratio,
            "p_value": float(p_value),
            "ci_lo": float(ci_lo),
            "ci_hi": float(ci_hi),
        })

    per_N = pd.DataFrame(rows)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(per_N["N"], per_N["ratio"], "o-", color="steelblue", label="observed/expected")
    ax.axhline(1.0, color="red", linestyle="--", label="ratio=1 (uniform null)")
    ax.set_xscale("log")
    ax.set_xlabel("N (assumed tickets per draw)")
    ax.set_ylabel("rollover rate ratio (observed / expected)")
    ax.set_title(f"Observed rollover rate = {observed_rate:.3f}")
    ax.legend()
    fig.tight_layout()

    return RolloverExcessResult(
        observed_rollover_rate=observed_rate,
        per_N=per_N,
        fig=fig,
    )
