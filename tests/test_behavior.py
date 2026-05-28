from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from math import comb

from stats.behavior import rollover_excess, RolloverExcessResult


def _jackpot_df_with_rate(rate: float, n: int = 1000) -> pd.DataFrame:
    """rate is the jackpot WIN rate. observed_rollover_rate will equal (1 - rate)."""
    rng = np.random.default_rng(0)
    wins = rng.random(n) < rate
    return pd.DataFrame({
        "draw": range(1, n + 1),
        "award": [30_000_000] * n,
        "jackpot_won": wins,                  # True iff jackpot won that draw
        "ambiguous": [False] * n,
        "floor_estimate": [30_000_000.0] * n,
    })


def test_rollover_excess_uniform_grid_ratio_near_one():
    """If observed rollover rate matches a specific N in the grid, ratio≈1 at that N."""
    range_, n_balls = 56, 6
    p = 1 / comb(range_, n_balls)
    N_target = 30_000_000  # picked so that exp(-N*p) ≈ specific value
    expected_rollover_rate = float(np.exp(-N_target * p))
    df = _jackpot_df_with_rate(rate=1 - expected_rollover_rate, n=2000)

    result = rollover_excess(
        df, range_=range_, n_balls=n_balls,
        n_players_grid=[N_target],
    )
    assert isinstance(result, RolloverExcessResult)
    assert len(result.per_N) == 1
    ratio = result.per_N.loc[0, "ratio"]
    assert 0.9 <= ratio <= 1.1


def test_rollover_excess_observed_above_expected_gives_ratio_gt_1():
    """If observed rollover rate exceeds the Poisson prediction, ratio > 1 at that N."""
    range_, n_balls = 56, 6
    p = 1 / comb(range_, n_balls)
    N = 30_000_000
    poisson_rollover_rate = float(np.exp(-N * p))
    # Simulate observed rollover rate higher than Poisson
    observed_rollover_rate = poisson_rollover_rate + 0.05
    rate_of_win = 1 - observed_rollover_rate
    df = _jackpot_df_with_rate(rate=rate_of_win, n=3000)

    result = rollover_excess(
        df, range_=range_, n_balls=n_balls,
        n_players_grid=[N],
    )
    assert result.per_N.loc[0, "ratio"] > 1.0


def test_rollover_excess_grid_produces_one_row_per_N():
    df = _jackpot_df_with_rate(rate=0.1, n=500)
    grid = [1_000_000, 5_000_000, 10_000_000]
    result = rollover_excess(df, range_=56, n_balls=6, n_players_grid=grid)
    assert list(result.per_N["N"]) == grid


from stats.db import load_draws
from stats.rollover import derive_jackpot_won


@pytest.mark.integration
def test_rollover_excess_melate_real_lower_bound(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    jackpot_df = derive_jackpot_won(data.draws_wide["award"])
    grid = [1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000]
    result = rollover_excess(jackpot_df, range_=data.range,
                             n_balls=data.n_balls, n_players_grid=grid)
    print(f"\nMelate observed rollover rate = {result.observed_rollover_rate:.3f}")
    print(result.per_N.to_string(index=False))
    # Lower bound: at the largest N (most favorable to null), ratio should still be ≥ 1
    largest_N_row = result.per_N.iloc[-1]
    assert largest_N_row["ratio"] >= 1.0, (
        "rollover excess vanishes at the largest N — either no conscious selection "
        "OR F0.5 is mis-detecting jackpot wins. Check first."
    )


from stats.behavior import rollover_excess_annual, AnnualRolloverExcessResult


def test_rollover_excess_annual_uniform_play_ratio_near_one():
    """Synthetic: simulate uniform play with known N; the calibrated annual
    test should recover a ratio close to 1."""
    rng = np.random.default_rng(0)
    range_, n_balls, p_any_win = 56, 6, 0.119
    p_jackpot = 1.0 / comb(range_, n_balls)
    N_per_sorteo = 1_500_000
    expected_rate = 1.0 - np.exp(-N_per_sorteo * p_jackpot)
    # Build 5 synthetic years × 156 sorteos each.
    rows = []
    dates = []
    for year in range(2019, 2024):
        for k in range(156):
            won = bool(rng.random() < expected_rate)
            rows.append({"draw": len(rows) + 1, "award": 30_000_000,
                         "jackpot_won": won, "ambiguous": False,
                         "floor_estimate": 30_000_000.0})
            dates.append(pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=k))
    jackpot_df = pd.DataFrame(rows)
    date_series = pd.Series(dates)

    # Construct annual_winners that is internally consistent with N_per_sorteo.
    annual_winners = pd.DataFrame([
        {"year": y, "winners": int(N_per_sorteo * p_any_win * 156)}
        for y in range(2019, 2024)
    ])
    result = rollover_excess_annual(
        jackpot_df, date_series, annual_winners,
        range_=range_, n_balls=n_balls, p_any_win=p_any_win,
    )
    assert isinstance(result, AnnualRolloverExcessResult)
    assert 0.7 < result.overall_ratio < 1.3, (
        f"calibrated ratio {result.overall_ratio:.3f} deviates from 1 under uniform play"
    )


from stats.ingest import load_annual_winners, p_any_win_per_ticket


@pytest.mark.integration
def test_rollover_excess_annual_melate_real(real_db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    monkeypatch.setenv("MELATE_DATOS_DIR", str(tmp_path / "datos"))
    data = load_draws("melate")
    jackpot_df = derive_jackpot_won(data.draws_wide["award"])
    annual = load_annual_winners().query("product == 'melate'")[["year", "winners"]]
    p_win = p_any_win_per_ticket(
        range_=data.range, n_balls=data.n_balls,
        has_additional=data.has_additional,
    )
    result = rollover_excess_annual(
        jackpot_df, data.draws_wide["date"], annual,
        range_=data.range, n_balls=data.n_balls, p_any_win=p_win,
    )
    print(f"\nMelate annual rollover-excess (calibrated N):")
    print(result.per_year[["year", "n_sorteos", "n_jackpots", "total_winners",
                            "n_calibrated_per_sorteo", "expected_jackpot_rate",
                            "observed_jackpot_rate", "ratio", "p_value"]].to_string(
        index=False, float_format=lambda v: f"{v:.4f}"
    ))
    print(f"Overall ratio={result.overall_ratio:.3f}, p={result.overall_p_value:.4f}")
    # Sanity: at least one year with both DB jackpots and XLSX winners.
    assert len(result.per_year) >= 5
    # Calibrated N per sorteo should be in millions, not 50M or 1k.
    assert result.per_year["n_calibrated_per_sorteo"].between(100_000, 50_000_000).all()
