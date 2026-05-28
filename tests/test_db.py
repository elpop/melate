from __future__ import annotations

import pytest

from stats.db import load_draws, DrawData, DataIntegrityError


def test_load_draws_melate_returns_product_metadata(tiny_db_path):
    data = load_draws("melate")
    assert isinstance(data, DrawData)
    assert data.product_name == "Melate"
    assert data.product_id == 40
    assert data.range == 56
    assert data.n_balls == 6
    assert data.has_additional is True


def test_load_draws_revancha_metadata(tiny_db_path):
    data = load_draws("revancha")
    assert data.product_id == 41
    assert data.range == 56
    assert data.has_additional is False


def test_load_draws_retro_metadata(tiny_db_path):
    data = load_draws("retro")
    assert data.product_id == 30
    assert data.range == 39
    assert data.has_additional is True


def test_load_draws_unknown_product_raises(tiny_db_path):
    with pytest.raises(ValueError, match="unknown product"):
        load_draws("powerball")


def test_load_draws_melate_populates_wide_and_long(tiny_db_path):
    data = load_draws("melate")
    # tiny_db_path seeds 50 draws per product
    assert len(data.draws_wide) == 50
    assert len(data.draws_long) == 50 * data.n_balls
    # draws_long has the right columns
    assert list(data.draws_long.columns) == ["draw", "date", "position", "ball"]
    # ball values in valid range
    assert data.draws_long["ball"].between(1, data.range).all()


def test_r7_normalized_to_int64_nullable_for_revancha(tiny_db_path):
    data = load_draws("revancha")
    # has_additional=False ⇒ r7_series is None
    assert data.r7_series is None
    # but draws_wide still has r7 column, and it must be Int64 with all <NA>
    assert data.draws_wide["r7"].dtype.name == "Int64"
    assert data.draws_wide["r7"].isna().all()


def test_r7_populated_int64_for_melate(tiny_db_path):
    data = load_draws("melate")
    assert data.r7_series is not None
    assert data.r7_series.dtype.name == "Int64"
    assert data.r7_series.notna().all()
    assert data.r7_series.between(1, data.range).all()


def test_draws_sorted_ascending_by_draw(tiny_db_path):
    data = load_draws("melate")
    draws = data.draws_wide["draw"].tolist()
    assert draws == sorted(draws)
