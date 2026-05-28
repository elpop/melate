"""Shared pytest fixtures: synthetic and real DB paths."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


PRODUCTS_SEED = [
    # (id, name, range, balls, additional, url, filename)
    (40, "Melate",       56, 6, 1, "", "Melate"),
    (41, "Revancha",     56, 6, 0, "", "Revancha"),
    (34, "Revanchita",   56, 6, 0, "", "Revanchita"),
    (30, "Melate Retro", 39, 6, 1, "", "Retro"),
]


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE products (
            id integer not null,
            name text not null,
            range integer not null,
            balls integer not null,
            additional integer not null,
            url text not null,
            filename text not null
        );
        CREATE UNIQUE INDEX un_p_id ON products(id);
        CREATE TABLE results (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            draw integer NOT NULL,
            date_time TEXT NOT NULL,
            r1 integer, r2 integer, r3 integer, r4 integer,
            r5 integer, r6 integer, r7 integer,
            award integer,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE UNIQUE INDEX un_pi_d_results ON results(product_id, draw);
        """
    )


def _seed_products(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO products(id,name,range,balls,additional,url,filename) "
        "VALUES (?,?,?,?,?,?,?)",
        PRODUCTS_SEED,
    )


def _seed_draws(conn: sqlite3.Connection, product_id: int, n_draws: int,
                range_: int, additional: int) -> None:
    """Insert n_draws synthetic draws for a product.

    r1..r6: deterministic permutation of 6 values in [1, range_] per draw.
    r7: integer in [1, range_] if additional==1, else '' (matches melate.pl:366).
    award: monotone-ish series with resets to a floor every ~15 draws.
    """
    import random

    rng = random.Random(product_id)
    floor = 30_000_000 if range_ == 56 else 5_000_000
    award = floor
    rows = []
    for k in range(1, n_draws + 1):
        balls = rng.sample(range(1, range_ + 1), 6)
        r7 = rng.randint(1, range_) if additional == 1 else ""
        if k % 15 == 0:
            award = floor  # simulated jackpot win → reset
        else:
            award += rng.randint(500_000, 3_000_000)
        rows.append((product_id, k, f"2024-01-{(k % 28) + 1:02d}",
                     *balls, r7, award))
    conn.executemany(
        "INSERT INTO results(product_id,draw,date_time,r1,r2,r3,r4,r5,r6,r7,award) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


@pytest.fixture
def tiny_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ephemeral SQLite with the real schema and ~50 synthetic draws per product.

    Scope: lógica only (parsing, normalization, edge cases). NOT statistical properties.
    """
    db_path = tmp_path / "melate.db"
    conn = sqlite3.connect(db_path)
    _create_schema(conn)
    _seed_products(conn)
    for pid, _name, range_, _balls, additional, *_ in PRODUCTS_SEED:
        _seed_draws(conn, pid, n_draws=50, range_=range_, additional=additional)
    conn.commit()
    conn.close()
    monkeypatch.setenv("MELATE_DB", str(db_path))
    return db_path


@pytest.fixture
def real_db_path() -> Path:
    """Path to the real ~/.melate/melate.db; skips if absent."""
    path = Path.home() / ".melate" / "melate.db"
    if not path.exists():
        pytest.skip("real Melate DB not present at ~/.melate/melate.db")
    return path
