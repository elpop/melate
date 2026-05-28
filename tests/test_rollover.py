from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.rollover import estimate_floor, FloorEstimateWarning


def test_estimate_floor_recovers_known_floor_with_clean_resets():
    floor = 30_000_000
    # 30 draws: accumulate, reset, accumulate, reset...
    awards = []
    current = floor
    for k in range(30):
        if k % 6 == 5:
            current = floor  # reset
        else:
            current += 5_000_000
        awards.append(current)
    s = pd.Series(awards)
    est = estimate_floor(s, eps=0.05)
    assert est == floor


def test_estimate_floor_warns_when_min_and_mode_disagree():
    """A single outlier should warn, but the recurrent mode wins as the floor."""
    awards = pd.Series([1] + [30_000_000] * 5 + [60_000_000] * 5 + [30_000_000] * 5)
    with pytest.warns(FloorEstimateWarning):
        est = estimate_floor(awards, eps=0.05)
    assert est == 30_000_000  # mode = recurrent reset value, not the outlier


def test_estimate_floor_filters_zero_awards():
    """award == 0 in the real CSV means missing data, not an actual reset value."""
    awards = pd.Series([0, 0, 0, 30_000_000, 30_000_000, 50_000_000, 80_000_000,
                        30_000_000, 30_000_000])
    est = estimate_floor(awards, eps=0.05)
    assert est == 30_000_000


from stats.rollover import derive_jackpot_won


def test_derive_jackpot_won_marks_reset_to_floor():
    floor = 30_000_000
    awards = pd.Series([floor, 50_000_000, 80_000_000, floor, 40_000_000])
    df = derive_jackpot_won(awards)
    # award[k+1] = floor and award[k] >= threshold * floor → True
    # draw indices align with award index
    assert df.loc[2, "jackpot_won"] is True or df.loc[2, "jackpot_won"] == True
    # last draw has no k+1 → NaN
    assert pd.isna(df.loc[4, "jackpot_won"])


def test_derive_jackpot_won_ignores_floor_with_no_buildup():
    """If award did not accumulate enough, do not call it a jackpot win."""
    floor = 30_000_000
    # award[k] is floor itself, then floor again → not a jackpot win
    awards = pd.Series([floor, floor, floor])
    df = derive_jackpot_won(awards)
    assert not df.loc[0, "jackpot_won"]
    assert not df.loc[1, "jackpot_won"]


def test_derive_jackpot_won_returns_expected_columns():
    awards = pd.Series([30_000_000] * 5)
    df = derive_jackpot_won(awards)
    assert set(df.columns) == {"draw", "award", "jackpot_won",
                               "ambiguous", "floor_estimate"}


from stats.db import load_draws


@pytest.mark.integration
def test_derive_jackpot_won_real_melate(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    df = derive_jackpot_won(data.draws_wide["award"])
    floor = df["floor_estimate"].iloc[0]
    assert 27_000_000 <= floor <= 35_000_000, (
        f"floor_estimate={floor} outside expected 27-35M for Melate"
    )
    ambiguous_rate = df["ambiguous"].mean()
    print(f"\nMelate floor={floor:.0f}, "
          f"jackpot_won rate={df['jackpot_won'].dropna().mean():.3f}, "
          f"ambiguous rate={ambiguous_rate:.3f}")
    assert ambiguous_rate < 0.05, (
        f"ambiguous rate {ambiguous_rate:.1%} > 5% sanity bound"
    )
