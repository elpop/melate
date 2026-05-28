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
