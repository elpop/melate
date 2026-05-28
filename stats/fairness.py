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
