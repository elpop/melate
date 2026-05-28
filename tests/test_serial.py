from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.serial import (
    runs_test, lag1_autocorrelation, serial_independence_per_ball,
    SerialResult,
)


def _wide_uniform(n_draws: int, range_: int, n_balls: int = 6,
                  seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [rng.choice(range_, size=n_balls, replace=False) + 1
            for _ in range(n_draws)]
    return pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, n_balls + 1)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def test_runs_test_iid_does_not_reject():
    rng = np.random.default_rng(0)
    x = rng.binomial(1, 0.107, size=2000)
    n_runs, expected_runs, z, p = runs_test(x)
    assert p > 0.01


def test_runs_test_clumpy_sequence_rejects():
    """Long runs of 0 followed by long runs of 1 → too few runs → reject."""
    x = np.array([0] * 200 + [1] * 200 + [0] * 200 + [1] * 200)
    n_runs, expected_runs, z, p = runs_test(x)
    assert n_runs < expected_runs / 2
    assert p < 1e-6


def test_lag1_autocorrelation_iid_near_zero():
    rng = np.random.default_rng(1)
    x = rng.binomial(1, 0.1, size=3000)
    rho, p = lag1_autocorrelation(x)
    assert abs(rho) < 0.06
    assert p > 0.05


def test_lag1_autocorrelation_alternating_pattern_detected():
    """1, 0, 1, 0, ... has strong negative lag-1 autocorrelation."""
    x = np.tile([1, 0], 500)
    rho, p = lag1_autocorrelation(x)
    assert rho < -0.9
    assert p < 1e-9


def test_serial_independence_per_ball_uniform_data_no_violation():
    wide = _wide_uniform(n_draws=2000, range_=56, seed=11)
    result = serial_independence_per_ball(wide, range_=56, n_balls=6)
    assert isinstance(result, SerialResult)
    assert len(result.per_ball) == 56
    cols = {"ball", "n_runs", "expected_runs", "z_runs", "p_runs",
            "lag1_autocorr", "p_lag1", "min_p", "significant_at_bonferroni"}
    assert cols <= set(result.per_ball.columns)
    assert result.n_significant_at_bonferroni == 0


def test_serial_independence_detects_alternating_injection():
    """Inject ball 7 in EVERY OTHER draw (strong negative lag-1 autocorr).
    The per-ball serial test must flag ball 7 after Bonferroni."""
    rng = np.random.default_rng(2)
    n_draws = 800
    rows = []
    for k in range(n_draws):
        if k % 2 == 0:
            others = rng.choice([b for b in range(1, 57) if b != 7],
                                size=5, replace=False)
            balls = [7] + list(others)
        else:
            balls = rng.choice([b for b in range(1, 57) if b != 7],
                               size=6, replace=False)
        rng.shuffle(balls)
        rows.append(list(balls))
    wide = pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, 7)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    result = serial_independence_per_ball(wide, range_=56, n_balls=6)
    row = result.per_ball[result.per_ball["ball"] == 7].iloc[0]
    assert bool(row["significant_at_bonferroni"]) is True


from stats.db import load_draws


@pytest.mark.integration
def test_serial_independence_melate_real_no_violation(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = serial_independence_per_ball(
        data.draws_wide, range_=data.range, n_balls=data.n_balls
    )
    print(f"\nMelate serial: nominal α=0.05 = {result.n_significant_at_nominal_05}/{data.range}; "
          f"Bonferroni = {result.n_significant_at_bonferroni}")
    assert result.n_significant_at_bonferroni == 0
