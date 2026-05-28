"""F0 — read-only access to ~/.melate/melate.db.

Loads draws of a product into a normalized DrawData. Path overridable via
the MELATE_DB env var (used by tests).
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PRODUCT_IDS: dict[str, int] = {
    "melate": 40,
    "revancha": 41,
    "revanchita": 34,
    "retro": 30,
}


# Per-product start of the current ball-range format. Earlier draws used
# a smaller range (Melate: 1-39 in 1984, 1-44 in 1993, etc.) and mixing
# eras in a chi-square test artificially rejects uniformity. Verified
# against the DB at 2026-05-28:
#   Melate (40):    range grew 39→44→47→50→51→56 between 1984 and 2007.
#   Revancha (41):  same migration, both products went 6/56 in 2007.
#   Revanchita (34) and Retro (30) started after the migration and have
#   been at their current range throughout.
DEFAULT_SINCE: dict[str, str | None] = {
    "melate":     "2007-01-01",
    "revancha":   "2007-01-01",
    "revanchita": None,
    "retro":      None,
}


class DataIntegrityError(RuntimeError):
    def __init__(self, draw: int, msg: str) -> None:
        super().__init__(f"draw {draw}: {msg}")
        self.draw = draw


@dataclass
class DrawData:
    product_name: str
    product_id: int
    range: int
    n_balls: int
    has_additional: bool
    draws_wide: pd.DataFrame
    draws_long: pd.DataFrame
    r7_series: pd.Series | None


def _db_path() -> Path:
    override = os.environ.get("MELATE_DB")
    if override:
        return Path(override)
    return Path.home() / ".melate" / "melate.db"


_SENTINEL_DEFAULT = object()


def load_draws(product: str, *, since=_SENTINEL_DEFAULT) -> DrawData:
    """Load all draws for a product into a DrawData.

    `since`: ISO date string ("YYYY-MM-DD") to filter draws by `date_time >= since`.
    If omitted, defaults to the per-product current-format start (see DEFAULT_SINCE)
    so chi-square and friends operate on a homogeneous ball-range era.
    Pass an explicit value to override (use "1900-01-01" to disable filtering).
    """
    if product not in PRODUCT_IDS:
        raise ValueError(f"unknown product: {product!r}")
    product_id = PRODUCT_IDS[product]

    if since is _SENTINEL_DEFAULT:
        since = DEFAULT_SINCE[product]

    conn = sqlite3.connect(_db_path())
    try:
        meta = conn.execute(
            "SELECT name, range, balls, additional FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if meta is None:
            raise ValueError(f"product id {product_id} not in DB")
        name, range_, n_balls, additional = meta
    finally:
        conn.close()

    # Load results with optional date filter.
    if since is None:
        query = (
            "SELECT draw, date_time, r1, r2, r3, r4, r5, r6, r7, award "
            "FROM results WHERE product_id = ? ORDER BY draw ASC"
        )
        params: tuple = (product_id,)
    else:
        query = (
            "SELECT draw, date_time, r1, r2, r3, r4, r5, r6, r7, award "
            "FROM results WHERE product_id = ? AND date_time >= ? "
            "ORDER BY draw ASC"
        )
        params = (product_id, since)

    conn = sqlite3.connect(_db_path())
    try:
        raw = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

    # Normalize r7: SQLite stores '' for Revancha/Revanchita (melate.pl:366);
    # coerce to nullable Int64 so NA stays NA.
    raw["r7"] = pd.to_numeric(raw["r7"], errors="coerce").astype("Int64")

    # date parsed to datetime, then renamed.
    raw["date_time"] = pd.to_datetime(raw["date_time"], format="%Y-%m-%d")
    raw = raw.rename(columns={"date_time": "date"})

    draws_wide = raw[["draw", "date", "r1", "r2", "r3", "r4", "r5", "r6",
                      "r7", "award"]].reset_index(drop=True)

    # Validate r1..r6.
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    for _, row in draws_wide.iterrows():
        balls = [row[c] for c in ball_cols]
        if len(set(balls)) != n_balls:
            raise DataIntegrityError(row["draw"], "duplicate balls in r1..r6")
        if not all(1 <= b <= range_ for b in balls):
            raise DataIntegrityError(row["draw"], f"ball out of [1, {range_}]")

    # Build long format from r1..r6 only.
    long = draws_wide[["draw", "date"] + ball_cols].melt(
        id_vars=["draw", "date"], value_vars=ball_cols,
        var_name="position", value_name="ball",
    ).sort_values(["draw", "position"]).reset_index(drop=True)

    # r7_series only if has_additional.
    if bool(additional):
        r7_series = draws_wide.set_index("draw")["r7"]
    else:
        r7_series = None

    return DrawData(
        product_name=name,
        product_id=product_id,
        range=range_,
        n_balls=n_balls,
        has_additional=bool(additional),
        draws_wide=draws_wide,
        draws_long=long,
        r7_series=r7_series,
    )
