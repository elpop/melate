"""Tarea 7 — multivariate co-occurrence vs hypergeometric.

Counts how often each pair of balls appears together in the same draw,
compares against the expectation under uniform 6-of-N draws, and reports
standardized residuals. Captures structural / pair-level physical bias
that the marginal frequencies (tarea 1) cannot see, because chi² on the
marginals is blind to a bias of the form "balls 7 and 23 co-occur more
than chance" when individually each still hits its expected frequency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy.stats import norm


@dataclass
class CooccurrenceResult:
    n_draws: int
    expected_per_pair: float
    bonferroni_threshold: float
    observed_matrix: np.ndarray          # shape (range_, range_), symmetric, diag=0
    z_matrix: np.ndarray                 # shape (range_, range_), diag=0
    max_abs_z: float
    n_extreme_at_nominal_05: int         # |z| > 1.96 (uncorrected)
    n_extreme_at_bonferroni: int         # |z| > Φ⁻¹(1 − α / (2·n_pairs))
    chi2_stat: float                     # sum z² over upper triangle
    fig: Figure


def _build_cooccurrence(draws_wide: pd.DataFrame, range_: int,
                        n_balls: int) -> np.ndarray:
    """Return a (range_+1) × (range_+1) matrix where M[i, j] counts draws
    that contain both ball i and ball j (1-indexed; row 0 / col 0 unused).
    The diagonal is forced to zero — a ball never co-occurs with itself."""
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    balls_per_draw = draws_wide[ball_cols].to_numpy(dtype=np.int64)
    m = np.zeros((range_ + 1, range_ + 1), dtype=np.int64)
    for row in balls_per_draw:
        # For this draw, increment M[i, j] for every unordered pair (i, j).
        for i_idx in range(n_balls):
            for j_idx in range(i_idx + 1, n_balls):
                a, b = row[i_idx], row[j_idx]
                m[a, b] += 1
                m[b, a] += 1
    return m


def cooccurrence_test(
    draws_wide: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    alpha: float = 0.05,
) -> CooccurrenceResult:
    full = _build_cooccurrence(draws_wide, range_=range_, n_balls=n_balls)
    # Drop the row 0 / col 0 padding to expose a clean (range_, range_) matrix.
    obs = full[1:, 1:]
    n_draws = len(draws_wide)

    # Probability that a specific unordered pair (i, j), i != j, appears in
    # one fair draw of n_balls without replacement from range_:
    #   P = C(range_ − 2, n_balls − 2) / C(range_, n_balls)
    #     = n_balls · (n_balls − 1) / (range_ · (range_ − 1))
    p_pair = n_balls * (n_balls - 1) / (range_ * (range_ - 1))
    expected = n_draws * p_pair
    var_pair = n_draws * p_pair * (1 - p_pair)
    sd_pair = np.sqrt(var_pair)

    z = (obs.astype(float) - expected) / sd_pair
    np.fill_diagonal(z, 0.0)

    iu = np.triu_indices(range_, k=1)
    z_upper = z[iu]
    n_pairs = len(z_upper)

    bonf_threshold = float(norm.ppf(1.0 - alpha / (2.0 * n_pairs)))
    n_nominal = int((np.abs(z_upper) > norm.ppf(1.0 - alpha / 2.0)).sum())
    n_bonf = int((np.abs(z_upper) > bonf_threshold).sum())
    chi2_stat = float((z_upper ** 2).sum())
    max_abs_z = float(np.abs(z_upper).max())

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 7))
    # Symmetric color scale around 0 so over/under-representation reads
    # the same magnitude visually.
    vmax = max(3.0, np.abs(z).max())
    im = ax.imshow(z, cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                   extent=(0.5, range_ + 0.5, range_ + 0.5, 0.5))
    cbar = fig.colorbar(im, ax=ax, label="z = (obs − expected) / σ")
    cbar.ax.axhline(bonf_threshold, color="black", linestyle="--", linewidth=0.5)
    cbar.ax.axhline(-bonf_threshold, color="black", linestyle="--", linewidth=0.5)
    ax.set_xlabel("ball j")
    ax.set_ylabel("ball i")
    ax.set_title(
        f"Co-occurrence z-scores  (n_draws={n_draws}, "
        f"expected/pair={expected:.1f})\n"
        f"max|z|={max_abs_z:.2f}; Bonferroni at {bonf_threshold:.2f}σ"
    )
    fig.tight_layout()

    return CooccurrenceResult(
        n_draws=n_draws,
        expected_per_pair=expected,
        bonferroni_threshold=bonf_threshold,
        observed_matrix=obs,
        z_matrix=z,
        max_abs_z=max_abs_z,
        n_extreme_at_nominal_05=n_nominal,
        n_extreme_at_bonferroni=n_bonf,
        chi2_stat=chi2_stat,
        fig=fig,
    )
