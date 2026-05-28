from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.fairness import chi_square_uniformity, ChiSquareResult


def test_chi_square_uniformity_returns_named_result():
    rng = np.random.default_rng(0)
    samples = pd.Series(rng.integers(1, 57, size=10_000))
    result = chi_square_uniformity(samples, n_categories=56)
    assert isinstance(result, ChiSquareResult)
    assert result.dof == 55
    assert 0.0 <= result.p_value <= 1.0
    assert result.observed.shape == (56,)
    assert pytest.approx(result.expected, rel=1e-9) == 10_000 / 56


def test_chi_square_uniform_input_does_not_reject():
    """A genuinely uniform sample should not reject the null."""
    rng = np.random.default_rng(42)
    samples = pd.Series(rng.integers(1, 57, size=100_000))
    result = chi_square_uniformity(samples, n_categories=56)
    assert result.p_value > 0.05


def test_chi_square_skewed_input_rejects():
    """A clearly skewed sample (one category over-represented) rejects."""
    rng = np.random.default_rng(1)
    samples = pd.Series(
        np.concatenate([rng.integers(1, 57, size=10_000),
                        np.full(2_000, 7)])
    )
    result = chi_square_uniformity(samples, n_categories=56)
    assert result.p_value < 1e-6


from stats.fairness import correct_pvalues


def test_correct_pvalues_bonferroni_kills_uniform_noise():
    rng = np.random.default_rng(0)
    pvals = pd.Series(rng.uniform(0, 1, size=56))
    result = correct_pvalues(pvals, method="bonferroni")
    assert list(result.columns) == ["pval_raw", "pval_corrected", "significant_at_05"]
    assert result["significant_at_05"].sum() == 0
    # without correction, ~5% would be "significant"
    assert (pvals < 0.05).sum() >= 1


def test_correct_pvalues_bonferroni_keeps_strong_signal():
    pvals = pd.Series([1e-9] + [0.5] * 55)
    result = correct_pvalues(pvals, method="bonferroni")
    assert result["significant_at_05"].iloc[0]
    assert not result["significant_at_05"].iloc[1:].any()


def test_correct_pvalues_fdr_bh_more_permissive_than_bonferroni():
    pvals = pd.Series([0.001, 0.002, 0.003] + [0.5] * 53)
    bonf = correct_pvalues(pvals, method="bonferroni")["significant_at_05"].sum()
    fdr = correct_pvalues(pvals, method="fdr_bh")["significant_at_05"].sum()
    assert fdr >= bonf


from scipy import stats
from stats.fairness import simulate_null


def _chi2_stat(draws_long_ball: np.ndarray, range_: int) -> float:
    counts = np.bincount(draws_long_ball, minlength=range_ + 1)[1:]
    expected = counts.sum() / range_
    return float(((counts - expected) ** 2 / expected).sum())


def test_simulate_null_chi2_has_sane_shape():
    """Empirical χ² under uniform draws has known sanity bounds.

    Note: the exact distribution is NOT χ²(gl=range-1) because a single
    draw picks n_balls without replacement; the per-draw constraint
    deflates the mean. Just check we are in the right ballpark and the
    distribution is well-behaved (positive, tight, no NaNs).
    """
    range_ = 56
    n_balls = 6
    n_draws = 500
    n_sim = 2_000

    dist = simulate_null(
        range_=range_, n_balls=n_balls, n_draws=n_draws, n_sim=n_sim,
        statistic_fn=lambda draws_long_ball: _chi2_stat(draws_long_ball, range_),
        seed=7,
    )
    assert dist.shape == (n_sim,)
    assert np.isfinite(dist).all()
    assert (dist > 0).all()
    # Mean of χ² without-replacement is ≈ (range-n_balls)/(range-1) · gl
    # = 50/55 · 55 = 50 for range=56, n_balls=6. Allow ±20% slack.
    assert 40 <= dist.mean() <= 60, f"mean {dist.mean():.1f} out of expected band"


def test_simulate_null_two_seeds_give_indistinguishable_distributions():
    """Internal-consistency check: distinct seeds → statistically same null."""
    kwargs = dict(
        range_=56, n_balls=6, n_draws=300, n_sim=2_000,
        statistic_fn=lambda x: _chi2_stat(x, 56),
    )
    dist_a = simulate_null(seed=1, **kwargs)
    dist_b = simulate_null(seed=2, **kwargs)
    ks_stat, ks_p = stats.ks_2samp(dist_a, dist_b)
    assert ks_p > 0.05, (
        f"two seeds produce different distributions: KS p={ks_p}"
    )


def test_simulate_null_seed_reproducible():
    dist_a = simulate_null(range_=56, n_balls=6, n_draws=100, n_sim=200,
                           statistic_fn=lambda x: float(x.sum()), seed=42)
    dist_b = simulate_null(range_=56, n_balls=6, n_draws=100, n_sim=200,
                           statistic_fn=lambda x: float(x.sum()), seed=42)
    np.testing.assert_array_equal(dist_a, dist_b)


from stats.db import load_draws


@pytest.mark.integration
def test_chi_square_melate_real_does_not_reject(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = chi_square_uniformity(data.draws_long["ball"], data.range)
    # Reportar p_value siempre. Sanity: p > 0.05 esperado.
    print(f"\nMelate χ²={result.stat:.2f}, dof={result.dof}, p={result.p_value:.4f}")
    assert result.p_value > 0.001, (
        f"χ² strongly rejects uniformity (p={result.p_value:.4e}); "
        "treat as suspected bug per design §3 anti-bug rule"
    )


from stats.fairness import bayesian_fairness, BayesianFairnessResult


def test_bayesian_fairness_returns_one_interval_per_category():
    rng = np.random.default_rng(0)
    samples = pd.Series(rng.integers(1, 57, size=10_000))
    result = bayesian_fairness(samples, n_categories=56)
    assert isinstance(result, BayesianFairnessResult)
    assert result.posterior_alpha.shape == (56,)
    assert len(result.credible_intervals_95) == 56
    assert set(result.credible_intervals_95.columns) >= {"ball", "mean", "lo", "hi"}


def test_bayesian_fairness_uniform_data_credible_intervals_contain_uniform():
    """Under genuinely uniform data, ~95% of CIs should contain 1/n_categories."""
    rng = np.random.default_rng(42)
    samples = pd.Series(rng.integers(1, 57, size=100_000))
    result = bayesian_fairness(samples, n_categories=56)
    # 95% CI → expect ≥ 90% containment in practice (some sampling slack)
    assert result.contains_uniform_count >= 50, (
        f"only {result.contains_uniform_count}/56 CIs contain uniform"
    )
    # Bayes factor should favor "fair" model
    assert result.log_bayes_factor_fair_vs_dirichlet > 0, (
        f"BF favors flexible model on uniform data: log BF={result.log_bayes_factor_fair_vs_dirichlet}"
    )


def test_bayesian_fairness_biased_data_few_cis_contain_uniform():
    """Strong over-representation of one ball → its CI must exclude uniform,
    and the Bayes factor must favor the flexible (biased) model."""
    rng = np.random.default_rng(1)
    samples = pd.Series(
        np.concatenate([rng.integers(1, 57, size=10_000),
                        np.full(4_000, 7)])  # ball 7 heavily over-represented
    )
    result = bayesian_fairness(samples, n_categories=56)
    # ball 7's CI must lie entirely above uniform
    ball7 = result.credible_intervals_95.iloc[6]  # ball=7 is row index 6
    uniform = 1.0 / 56
    assert ball7["lo"] > uniform
    # BF must clearly favor flexible (log BF << 0)
    assert result.log_bayes_factor_fair_vs_dirichlet < -10


@pytest.mark.integration
def test_bayesian_fairness_melate_real_favors_fair_model(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = bayesian_fairness(data.draws_long["ball"], data.range)
    print(f"\nMelate Bayesian: log BF={result.log_bayes_factor_fair_vs_dirichlet:.2f}, "
          f"CIs containing uniform: {result.contains_uniform_count}/{data.range}")
    # On the homogeneous era, the fair model must be preferred.
    assert result.log_bayes_factor_fair_vs_dirichlet > 0
    # Most CIs should contain uniform (95% nominally; allow ≥ 85% in real data).
    assert result.contains_uniform_count >= int(0.85 * data.range)
