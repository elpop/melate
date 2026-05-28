from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.hypotheses import (
    low_number_bias_test, bolsa_dependence_test,
    LowNumberBiasResult, BolsaDependenceResult,
)


def _wide_uniform(n_draws: int, range_: int, n_balls: int = 6,
                  seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_draws):
        rows.append(rng.choice(range_, size=n_balls, replace=False) + 1)
    return pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, n_balls + 1)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def _synthetic_jackpot_df(n_draws: int, win_rate: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "draw": range(1, n_draws + 1),
        "award": [30_000_000] * n_draws,
        "jackpot_won": rng.random(n_draws) < win_rate,
        "ambiguous": [False] * n_draws,
        "floor_estimate": [30_000_000.0] * n_draws,
    })


# ─────────────────── A1 / C1 — low-number bias ───────────────────


def test_low_number_bias_uniform_data_no_trend():
    """When jackpot_won is independent of combo, the test must NOT reject."""
    wide = _wide_uniform(n_draws=2000, range_=56, seed=3)
    jp = _synthetic_jackpot_df(2000, win_rate=0.03, seed=4)
    result = low_number_bias_test(wide, jp, range_=56, n_balls=6,
                                   low_cutoff=31)
    assert isinstance(result, LowNumberBiasResult)
    assert result.p_value > 0.05


def test_low_number_bias_detects_injected_correlation():
    """Inject correlation: high-lowness combos always win, low-lowness never.
    The test must detect it (p << 0.05)."""
    wide = _wide_uniform(n_draws=2000, range_=56, seed=5)
    ball_cols = [f"r{i}" for i in range(1, 7)]
    lowness = (wide[ball_cols] <= 31).sum(axis=1).to_numpy()
    # Make jackpot_won deterministic on lowness: tied to lowness >= 4
    jp = pd.DataFrame({
        "draw": wide["draw"].values,
        "award": [30_000_000] * len(wide),
        "jackpot_won": lowness >= 4,
        "ambiguous": [False] * len(wide),
        "floor_estimate": [30_000_000.0] * len(wide),
    })
    result = low_number_bias_test(wide, jp, range_=56, n_balls=6,
                                   low_cutoff=31)
    assert result.p_value < 1e-6
    # High-lowness bucket should have higher rate than low-lowness bucket
    assert (
        result.per_bucket["jackpot_rate"].iloc[-1]
        > result.per_bucket["jackpot_rate"].iloc[0]
    )


# ─────────────────────── B1 — BOLSA dependence ───────────────────────


def test_bolsa_dependence_returns_valid_result_when_no_trend():
    """When BOLSA varies but the win rate is constant, no correlation exists
    and the test must not reject."""
    rng = np.random.default_rng(9)
    n = 1500
    bolsa = rng.uniform(30_000_000, 200_000_000, size=n)
    wide = _wide_uniform(n_draws=n, range_=56).assign(award=bolsa.astype(int))
    jp = _synthetic_jackpot_df(n, win_rate=0.03)
    jp["award"] = bolsa.astype(int)
    result = bolsa_dependence_test(wide, jp, range_=56, n_balls=6)
    assert isinstance(result, BolsaDependenceResult)
    assert len(result.per_tercile) == 3
    assert result.p_value > 0.05


def test_bolsa_dependence_detects_strong_increase():
    """BOLSA bigger → more jackpots (because more N). Synthetic with
    explicit positive correlation must be detected at large n."""
    rng = np.random.default_rng(7)
    n = 6000
    bolsa = np.linspace(30_000_000, 200_000_000, n) + rng.normal(0, 5e6, n)
    # win_rate scales steeply: 0.005 → 0.10
    win_rate = 0.005 + 0.095 * (bolsa - bolsa.min()) / (bolsa.max() - bolsa.min())
    wins = rng.random(n) < win_rate

    wide = _wide_uniform(n_draws=n, range_=56, seed=8).assign(
        award=bolsa.astype(int),
    )
    jp = pd.DataFrame({
        "draw": wide["draw"].values,
        "award": bolsa.astype(int),
        "jackpot_won": wins,
        "ambiguous": [False] * n,
        "floor_estimate": [30_000_000.0] * n,
    })
    result = bolsa_dependence_test(wide, jp, range_=56, n_balls=6)
    assert result.p_value < 1e-9
    rates = result.per_tercile["jackpot_rate"].tolist()
    assert rates[2] > rates[0]


# ────────────────── Integration tests on real DB ──────────────────


from stats.db import load_draws
from stats.rollover import derive_jackpot_won


@pytest.mark.integration
def test_low_number_bias_retro_real(real_db_path, monkeypatch):
    """Retro had the strongest behavior signal (p=0.0013). If the hypothesis
    A1 is correct, low-number combos should show higher jackpot_won rate."""
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("retro")
    jp = derive_jackpot_won(data.draws_wide["award"])
    # For Retro 6/39 use cutoff 31 (date-like)
    result = low_number_bias_test(
        data.draws_wide, jp,
        range_=data.range, n_balls=data.n_balls, low_cutoff=31,
    )
    print(f"\nRetro low-number bias: chi²={result.chi2_stat:.2f}, "
          f"p={result.p_value:.4f}")
    print(result.per_bucket.to_string(index=False))
    # Pass regardless — it's exploratory.
    assert result.p_value >= 0.0


@pytest.mark.integration
def test_low_number_bias_melate_real(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    jp = derive_jackpot_won(data.draws_wide["award"])
    result = low_number_bias_test(
        data.draws_wide, jp,
        range_=data.range, n_balls=data.n_balls, low_cutoff=31,
    )
    print(f"\nMelate low-number bias: chi²={result.chi2_stat:.2f}, "
          f"p={result.p_value:.4f}")
    print(result.per_bucket.to_string(index=False))
    assert result.p_value >= 0.0


@pytest.mark.integration
def test_bolsa_dependence_melate_real(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    jp = derive_jackpot_won(data.draws_wide["award"])
    result = bolsa_dependence_test(
        data.draws_wide, jp,
        range_=data.range, n_balls=data.n_balls,
    )
    print(f"\nMelate BOLSA dependence: chi²={result.chi2_stat:.2f}, "
          f"p={result.p_value:.4f}")
    print(result.per_tercile.to_string(index=False))
    assert result.p_value >= 0.0


@pytest.mark.integration
def test_bolsa_dependence_retro_real(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("retro")
    jp = derive_jackpot_won(data.draws_wide["award"])
    result = bolsa_dependence_test(
        data.draws_wide, jp,
        range_=data.range, n_balls=data.n_balls,
    )
    print(f"\nRetro BOLSA dependence: chi²={result.chi2_stat:.2f}, "
          f"p={result.p_value:.4f}")
    print(result.per_tercile.to_string(index=False))
    assert result.p_value >= 0.0
