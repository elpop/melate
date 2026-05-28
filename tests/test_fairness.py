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
