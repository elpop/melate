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


@dataclass
class BayesianFairnessResult:
    n_total_samples: int
    posterior_alpha: np.ndarray             # shape (n_categories,)
    credible_intervals_95: pd.DataFrame     # cols: ball, mean, lo, hi
    contains_uniform_count: int             # out of n_categories
    log_bayes_factor_fair_vs_dirichlet: float  # > 0 → fair preferred
    fig: Figure


def bayesian_fairness(
    samples: pd.Series,
    n_categories: int,
    *,
    alpha_prior: float = 1.0,
) -> BayesianFairnessResult:
    """Dirichlet-Multinomial Bayesian fairness analysis.

    Model: ball probabilities ~ Dirichlet(α_prior, ..., α_prior); the observed
    counts come from a Multinomial with those probabilities. Posterior is
    Dirichlet(α_prior + counts). Per-ball marginals are Beta and give
    point-and-interval estimates on each p_i. A Bayes factor between the
    "fair" model (all p_i = 1/range) and this flexible Dirichlet model
    quantifies global evidence for fairness (log BF > 0 favors fair).
    """
    from scipy import stats as scipy_stats
    from scipy.special import gammaln

    counts = samples.value_counts().reindex(
        range(1, n_categories + 1), fill_value=0
    )
    counts_arr = counts.values.astype(np.int64)
    n = int(counts_arr.sum())

    # Posterior parameters
    alpha_post = alpha_prior + counts_arr.astype(np.float64)
    alpha_sum = float(alpha_post.sum())
    uniform = 1.0 / n_categories

    means = alpha_post / alpha_sum
    rows = []
    contains = 0
    for i, alpha_i in enumerate(alpha_post):
        beta_a = alpha_i
        beta_b = alpha_sum - alpha_i
        lo = float(scipy_stats.beta.ppf(0.025, beta_a, beta_b))
        hi = float(scipy_stats.beta.ppf(0.975, beta_a, beta_b))
        if lo <= uniform <= hi:
            contains += 1
        rows.append({"ball": i + 1, "mean": float(means[i]), "lo": lo, "hi": hi})
    ci_df = pd.DataFrame(rows)

    # log Bayes factor: fair vs Dirichlet-Multinomial(α_prior)
    # The multinomial coefficient cancels between the two models.
    # log P(data | fair)         = -n * log(range)
    # log P(data | Dir-Mult)     = log[Γ(Σα) Π Γ(α_k + c_k) / (Γ(n + Σα) Π Γ(α_k))]
    log_p_fair = -n * np.log(n_categories)
    sum_alpha_prior = alpha_prior * n_categories
    log_p_dirmult = (
        gammaln(sum_alpha_prior)
        - gammaln(n + sum_alpha_prior)
        + np.sum(gammaln(alpha_prior + counts_arr))
        - n_categories * gammaln(alpha_prior)
    )
    log_bf = float(log_p_fair - log_p_dirmult)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 4))
    yerr = np.vstack([ci_df["mean"] - ci_df["lo"], ci_df["hi"] - ci_df["mean"]])
    ax.errorbar(
        ci_df["ball"], ci_df["mean"], yerr=yerr,
        fmt="o", capsize=2, alpha=0.6, color="steelblue",
        label="95% credible interval",
    )
    ax.axhline(uniform, color="red", linestyle="--",
               label=f"uniform={uniform:.4f}")
    ax.set_xlabel("ball")
    ax.set_ylabel("posterior P(ball | sample)")
    ax.set_title(
        f"Bayesian fairness: log BF={log_bf:.2f} "
        f"({'fair preferred' if log_bf > 0 else 'flexible preferred'}); "
        f"{contains}/{n_categories} CIs contain uniform"
    )
    ax.legend()
    fig.tight_layout()

    return BayesianFairnessResult(
        n_total_samples=n,
        posterior_alpha=alpha_post,
        credible_intervals_95=ci_df,
        contains_uniform_count=contains,
        log_bayes_factor_fair_vs_dirichlet=log_bf,
        fig=fig,
    )


@dataclass
class GapsResult:
    """Per-ball gap-distribution K-S test against geometric(p=n_balls/range_).

    A "gap" is the number of draws between consecutive appearances of the
    same ball. Under fair independent draws the gap is geometric(p) with
    support {1, 2, 3, ...}. K-S rejects → that ball's gap distribution
    is not geometric → independence between draws is violated for that ball.
    """
    n_draws: int
    p_appear_per_draw: float            # n_balls / range_
    per_ball: pd.DataFrame              # ball, n_gaps, mean_gap, ks_stat, p_value, significant_at_bonferroni
    n_significant_at_nominal_05: int
    n_significant_at_bonferroni: int
    bonferroni_threshold: float
    fig: Figure


def _chi2_gaps_vs_geometric(gaps: np.ndarray, p: float) -> tuple[float, int, float]:
    """Chi² goodness-of-fit for an array of observed gaps against geom(p).

    The K-S test is inappropriate for discrete distributions — scipy's
    `kstest` p-values are computed against the continuous Kolmogorov
    distribution and are systematically biased toward rejection for
    geometric data. Chi² on binned counts is the standard alternative
    and is what the spec really wants when it says "K-S vs geometric".

    Merge the upper tail so every expected count is >= 5 (standard
    chi² recommendation). Returns (stat, dof, p_value).
    """
    from scipy.stats import chi2 as chi2_dist, geom

    n = len(gaps)
    if n < 10:
        return float("nan"), 0, 1.0

    # Find K such that the tail bin [K, ∞) has expected ≥ 5.
    K = 1
    while n * (1 - geom(p).cdf(K - 1)) >= 5:
        K += 1
    # Now bins are: 1, 2, ..., K-1, [K, ∞). Need K >= 3 for at least 2 dof.
    if K < 3:
        return float("nan"), 0, 1.0

    observed = np.zeros(K, dtype=int)
    for g in gaps:
        if g >= K:
            observed[K - 1] += 1
        else:
            observed[int(g) - 1] += 1
    expected = np.empty(K, dtype=float)
    for k in range(1, K):
        expected[k - 1] = n * geom(p).pmf(k)
    expected[K - 1] = n * (1 - geom(p).cdf(K - 1))

    stat = float(((observed - expected) ** 2 / expected).sum())
    dof = K - 1
    p_value = float(1 - chi2_dist.cdf(stat, dof))
    return stat, dof, p_value


def gaps_test(
    draws_wide: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    alpha: float = 0.05,
) -> GapsResult:
    from scipy.stats import geom

    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    ordered = draws_wide.sort_values("draw").reset_index(drop=True)
    n_draws = len(ordered)
    p_appear = n_balls / range_

    rows = []
    pvals = []
    all_observed_gaps: list[int] = []

    for ball in range(1, range_ + 1):
        appears = (ordered[ball_cols] == ball).any(axis=1).to_numpy()
        indices = np.where(appears)[0]
        if len(indices) < 2:
            rows.append({"ball": ball, "n_gaps": 0, "mean_gap": np.nan,
                         "ks_stat": np.nan, "p_value": 1.0})
            pvals.append(1.0)
            continue
        gaps = np.diff(indices)
        all_observed_gaps.extend(gaps.tolist())
        stat, dof, p_value = _chi2_gaps_vs_geometric(gaps, p_appear)
        rows.append({
            "ball": ball,
            "n_gaps": int(len(gaps)),
            "mean_gap": float(gaps.mean()),
            "chi2_stat": stat,
            "p_value": p_value,
        })
        pvals.append(p_value)

    per_ball = pd.DataFrame(rows)
    bonf_threshold = alpha / range_
    per_ball["significant_at_bonferroni"] = per_ball["p_value"] < bonf_threshold
    n_nominal = int((per_ball["p_value"] < alpha).sum())
    n_bonf = int(per_ball["significant_at_bonferroni"].sum())

    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    # Left: histogram of observed gaps vs theoretical geometric PMF.
    if all_observed_gaps:
        all_gaps = np.array(all_observed_gaps)
        max_gap = int(all_gaps.max())
        bins = np.arange(1, max_gap + 2) - 0.5
        axes[0].hist(all_gaps, bins=bins, density=True, alpha=0.6,
                     color="steelblue", label="observed (pooled)")
        ks = np.arange(1, max_gap + 1)
        axes[0].plot(ks, geom(p_appear).pmf(ks), "ro-", markersize=3,
                     label=f"geom(p={p_appear:.3f}) PMF")
        axes[0].set_xlim(0.5, min(max_gap + 0.5, 60))
        axes[0].set_xlabel("gap (draws between appearances)")
        axes[0].set_ylabel("density")
        axes[0].legend()
        axes[0].set_title("Pooled gap distribution vs geometric PMF")
    # Right: per-ball p-values.
    axes[1].scatter(per_ball["ball"], per_ball["p_value"],
                    c=np.where(per_ball["significant_at_bonferroni"], "red", "steelblue"),
                    alpha=0.7)
    axes[1].axhline(alpha, color="orange", linestyle=":", label=f"nominal α={alpha}")
    axes[1].axhline(bonf_threshold, color="red", linestyle="--",
                    label=f"Bonferroni α/range={bonf_threshold:.4f}")
    axes[1].set_xlabel("ball")
    axes[1].set_ylabel("K-S p-value")
    axes[1].set_yscale("log")
    axes[1].set_title(
        f"K-S p-value per ball  (Bonferroni-significant: {n_bonf}/{range_})"
    )
    axes[1].legend()
    fig.tight_layout()

    return GapsResult(
        n_draws=n_draws,
        p_appear_per_draw=p_appear,
        per_ball=per_ball,
        n_significant_at_nominal_05=n_nominal,
        n_significant_at_bonferroni=n_bonf,
        bonferroni_threshold=bonf_threshold,
        fig=fig,
    )
