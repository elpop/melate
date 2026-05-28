from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.multivariate import cooccurrence_test, CooccurrenceResult


def _wide_uniform(n_draws: int, range_: int, n_balls: int = 6,
                  seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [rng.choice(range_, size=n_balls, replace=False) + 1
            for _ in range(n_draws)]
    return pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, n_balls + 1)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def test_cooccurrence_returns_named_result_with_symmetric_matrix():
    wide = _wide_uniform(n_draws=500, range_=56)
    result = cooccurrence_test(wide, range_=56, n_balls=6)
    assert isinstance(result, CooccurrenceResult)
    obs = result.observed_matrix
    assert obs.shape == (56, 56)
    # symmetric
    np.testing.assert_array_equal(obs, obs.T)
    # diagonal: ball never co-occurs with itself in a single draw, so zero
    assert (np.diag(obs) == 0).all()


def test_cooccurrence_uniform_data_no_bonferroni_violation():
    """Under genuinely uniform draws, zero pairs should clear Bonferroni
    (in expectation), and the count at nominal α=0.05 sits near 5% of pairs."""
    wide = _wide_uniform(n_draws=2000, range_=56, seed=7)
    result = cooccurrence_test(wide, range_=56, n_balls=6)
    n_pairs = 56 * 55 // 2  # 1540
    # Nominal: ~5% pairs over |z| > 1.96 → ~77 in expectation; allow [40, 120]
    assert 30 <= result.n_extreme_at_nominal_05 <= 130
    # After Bonferroni correction: should be 0 (with high probability).
    assert result.n_extreme_at_bonferroni == 0


def test_cooccurrence_forced_pair_shows_extreme_z():
    """Inject one pair into every draw → that pair must clear Bonferroni
    and be the maximum z in the matrix."""
    rng = np.random.default_rng(2)
    n_draws = 1000
    rows = []
    for _ in range(n_draws):
        # Force balls 7 and 23 to co-occur; pick 4 other distinct balls.
        others = rng.choice([b for b in range(1, 57) if b not in (7, 23)],
                            size=4, replace=False)
        balls = [7, 23] + list(others)
        rng.shuffle(balls)
        rows.append(balls)
    wide = pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, 7)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    result = cooccurrence_test(wide, range_=56, n_balls=6)
    # Pair (7, 23) MUST be the max |z| and clearly above Bonferroni
    assert result.n_extreme_at_bonferroni >= 1
    # The (7-1, 23-1) index in the z matrix is the forced pair
    z_forced = result.z_matrix[6, 22]
    assert z_forced > result.bonferroni_threshold


from stats.db import load_draws


@pytest.mark.integration
def test_cooccurrence_melate_real_no_pair_survives_bonferroni(
    real_db_path, monkeypatch
):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = cooccurrence_test(data.draws_wide, range_=data.range,
                                n_balls=data.n_balls)
    n_pairs = data.range * (data.range - 1) // 2
    print(f"\nMelate co-occurrence: max|z|={result.max_abs_z:.2f}; "
          f"extreme at α=0.05: {result.n_extreme_at_nominal_05}/{n_pairs} "
          f"(~5% expected = {n_pairs * 0.05:.0f}); "
          f"extreme at Bonferroni ({result.bonferroni_threshold:.2f}σ): "
          f"{result.n_extreme_at_bonferroni}")
    # Spec expectation: no pair survives Bonferroni correction.
    assert result.n_extreme_at_bonferroni == 0
