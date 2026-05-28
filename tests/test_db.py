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
