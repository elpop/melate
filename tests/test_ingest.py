from __future__ import annotations

from pathlib import Path
import sqlite3
import pandas as pd
import pytest

from stats.ingest import load_annual_winners, p_any_win_per_ticket


def test_p_any_win_melate():
    """Melate 6/56 with adicional. Player wins anything if matches ≥2 main."""
    p = p_any_win_per_ticket(range_=56, n_balls=6, has_additional=True)
    # P(≥2 main of 6 from 56) ≈ 0.119
    assert 0.115 < p < 0.123


def test_p_any_win_revancha():
    """Revancha 6/56 no adicional. Player wins anything if matches ≥2 main."""
    p = p_any_win_per_ticket(range_=56, n_balls=6, has_additional=False)
    assert 0.115 < p < 0.123


def test_p_any_win_retro_higher_than_melate():
    """Retro 6/39 reaches further down the prize ladder (1 main + adic),
    so its per-ticket P(win) is higher than Melate, but only modestly
    because the low-tier categories are gated by the adicional probability."""
    p_retro = p_any_win_per_ticket(range_=39, n_balls=6, has_additional=True)
    p_melate = p_any_win_per_ticket(range_=56, n_balls=6, has_additional=True)
    assert p_retro > p_melate
    # Both are in the same order of magnitude (low teens %)
    assert 0.05 < p_retro < 0.20


def test_load_annual_winners_returns_long_dataframe(tmp_path, monkeypatch):
    """Smoke-test ingest end-to-end against the real file URL.
    Skips if network is unavailable; this is an integration-flavored test."""
    monkeypatch.setenv("MELATE_DATOS_DIR", str(tmp_path / "datos"))
    try:
        df = load_annual_winners(force_download=True)
    except Exception as e:
        pytest.skip(f"network unavailable or upstream layout changed: {e}")
    assert {"product", "year", "winners"} <= set(df.columns)
    # At least some Melate rows from 2015-2024 must be present.
    melate_rows = df[df["product"] == "melate"]
    assert len(melate_rows) >= 5
    assert melate_rows["year"].between(2015, 2030).all()
    # Total winners across the decade must be > 100M.
    assert melate_rows["winners"].sum() > 100_000_000
