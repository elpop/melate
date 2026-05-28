from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.drift import pettitt_test, pettitt_per_ball, DriftResult


def _wide_uniform(n_draws: int, range_: int, n_balls: int = 6,
                  seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [rng.choice(range_, size=n_balls, replace=False) + 1
            for _ in range(n_draws)]
    return pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, n_balls + 1)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def test_pettitt_test_returns_change_point_and_pvalue():
    rng = np.random.default_rng(0)
    x = rng.binomial(1, 0.1, size=500)
    stat, p_value, cp = pettitt_test(x)
    assert stat >= 0
    assert 0.0 <= p_value <= 1.0
    assert 0 <= cp < len(x)


def test_pettitt_uniform_iid_does_not_reject():
    """Bernoulli(p) iid → no change-point → p-value > 0.05 with high prob."""
    rng = np.random.default_rng(2)
    x = rng.binomial(1, 0.1, size=2000)
    _, p, _ = pettitt_test(x)
    assert p > 0.05


def test_pettitt_detects_clear_shift_in_mean():
    """Switch from p=0.05 in the first half to p=0.30 in the second half →
    Pettitt must reject strongly and find the change-point near the middle."""
    rng = np.random.default_rng(3)
    x1 = rng.binomial(1, 0.05, size=500)
    x2 = rng.binomial(1, 0.30, size=500)
    x = np.concatenate([x1, x2])
    stat, p, cp = pettitt_test(x)
    assert p < 1e-6
    # change point should be within ±50 of the true switch at index 500
    assert 450 <= cp <= 550


def test_pettitt_per_ball_returns_one_row_per_ball_with_bonferroni_flag():
    wide = _wide_uniform(n_draws=1000, range_=56)
    result = pettitt_per_ball(wide, range_=56, n_balls=6)
    assert isinstance(result, DriftResult)
    assert len(result.per_ball) == 56
    assert {"ball", "stat", "p_value", "change_point_index",
            "significant_at_bonferroni"} <= set(result.per_ball.columns)


def test_pettitt_per_ball_uniform_data_no_ball_survives_bonferroni():
    wide = _wide_uniform(n_draws=2000, range_=56, seed=7)
    result = pettitt_per_ball(wide, range_=56, n_balls=6)
    assert result.n_significant_at_bonferroni == 0


def test_pettitt_per_ball_detects_localized_bias():
    """Inject ball 13 over-represented in second half only → Pettitt for
    ball 13 must reject after Bonferroni."""
    rng = np.random.default_rng(4)
    n_draws = 1500
    rows = []
    for k in range(n_draws):
        # In the second half, force ball 13 in 30% of draws on top of normal.
        force_13 = (k >= n_draws // 2) and (rng.random() < 0.30)
        if force_13:
            others = rng.choice([b for b in range(1, 57) if b != 13],
                                size=5, replace=False)
            balls = [13] + list(others)
        else:
            balls = rng.choice(56, size=6, replace=False) + 1
        rng.shuffle(balls)
        rows.append(list(balls))
    wide = pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, 7)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    result = pettitt_per_ball(wide, range_=56, n_balls=6)
    row = result.per_ball[result.per_ball["ball"] == 13].iloc[0]
    assert bool(row["significant_at_bonferroni"]) is True
    # Change point should be roughly at the half-way mark.
    assert abs(int(row["change_point_index"]) - n_draws // 2) < n_draws * 0.10


from stats.db import load_draws


@pytest.mark.integration
def test_pettitt_per_ball_melate_real(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = pettitt_per_ball(data.draws_wide, range_=data.range,
                              n_balls=data.n_balls)
    print(f"\nMelate drift: nominal α=0.05 = {result.n_significant_at_nominal_05}/{data.range}; "
          f"Bonferroni = {result.n_significant_at_bonferroni}")
    assert result.n_significant_at_bonferroni == 0


@pytest.mark.integration
def test_pettitt_per_ball_retro_ball_24_diagnosis(real_db_path, monkeypatch):
    """The gaps test flagged Retro ball 24 (p_corr ≈ 0.04). Pettitt should
    say whether the deviation is temporally localized or persistent."""
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("retro")
    result = pettitt_per_ball(data.draws_wide, range_=data.range,
                              n_balls=data.n_balls)
    row = result.per_ball[result.per_ball["ball"] == 24].iloc[0]
    print(f"\nRetro ball 24: Pettitt stat={row['stat']:.2f}, "
          f"p={row['p_value']:.4f}, "
          f"change_point_draw_index={int(row['change_point_index'])}, "
          f"sig@Bonferroni={bool(row['significant_at_bonferroni'])}")
    # We don't assert pass/fail here; the test is purely diagnostic and
    # passes regardless to keep the report flow honest.
    assert isinstance(bool(row["significant_at_bonferroni"]), bool)
