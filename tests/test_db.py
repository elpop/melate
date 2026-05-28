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


def test_load_draws_raises_on_duplicate_balls(tmp_path, monkeypatch):
    """Inject a corrupt draw into a fresh tiny DB and check we catch it."""
    import sqlite3
    db = tmp_path / "corrupt.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE products (id integer, name text, range integer,
            balls integer, additional integer, url text, filename text);
        CREATE TABLE results (id INTEGER PRIMARY KEY, product_id INTEGER,
            draw integer, date_time TEXT, r1 integer, r2 integer, r3 integer,
            r4 integer, r5 integer, r6 integer, r7 integer, award integer);
        """
    )
    conn.execute(
        "INSERT INTO products VALUES (40,'Melate',56,6,1,'','Melate')"
    )
    # r1 == r2 → duplicate
    conn.execute(
        "INSERT INTO results(product_id,draw,date_time,r1,r2,r3,r4,r5,r6,r7,award)"
        " VALUES (40, 1, '2024-01-01', 5, 5, 6, 7, 8, 9, 10, 30000000)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("MELATE_DB", str(db))
    with pytest.raises(DataIntegrityError) as exc:
        load_draws("melate")
    assert exc.value.draw == 1


@pytest.mark.integration
def test_load_draws_real_db_matches_count(real_db_path, monkeypatch):
    """N from load_draws(since='1900-01-01') must match SELECT COUNT(*) for every product."""
    import sqlite3
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    conn = sqlite3.connect(real_db_path)
    try:
        for name, pid in [("melate", 40), ("revancha", 41),
                          ("revanchita", 34), ("retro", 30)]:
            expected = conn.execute(
                "SELECT COUNT(*) FROM results WHERE product_id = ?", (pid,)
            ).fetchone()[0]
            data = load_draws(name, since="1900-01-01")  # disable era filter
            assert len(data.draws_wide) == expected, (
                f"{name}: load_draws gave {len(data.draws_wide)}, DB has {expected}"
            )
    finally:
        conn.close()


@pytest.mark.integration
def test_load_draws_default_filters_to_current_format_era(real_db_path, monkeypatch):
    """Default since for Melate/Revancha is 2008-01-01; result must contain only
    draws under the 6/56 format with the stable 30M floor."""
    import pandas as pd
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    melate_full = load_draws("melate", since="1900-01-01")
    melate_filtered = load_draws("melate")
    # The filter must drop a substantial chunk of pre-2008 draws.
    assert len(melate_filtered.draws_wide) < len(melate_full.draws_wide) - 100
    # Max ball under filtered era must be exactly 56.
    max_ball = melate_filtered.draws_wide[
        ["r1", "r2", "r3", "r4", "r5", "r6"]
    ].max().max()
    assert max_ball == 56
    assert melate_filtered.draws_wide["date"].min() >= pd.Timestamp("2008-01-01")
