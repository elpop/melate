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


def load_draws(product: str) -> DrawData:
    if product not in PRODUCT_IDS:
        raise ValueError(f"unknown product: {product!r}")
    product_id = PRODUCT_IDS[product]

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

    empty_wide = pd.DataFrame(columns=["draw", "date", "r1", "r2", "r3", "r4",
                                       "r5", "r6", "r7", "award"])
    empty_long = pd.DataFrame(columns=["draw", "date", "position", "ball"])

    return DrawData(
        product_name=name,
        product_id=product_id,
        range=range_,
        n_balls=n_balls,
        has_additional=bool(additional),
        draws_wide=empty_wide,
        draws_long=empty_long,
        r7_series=None,
    )
