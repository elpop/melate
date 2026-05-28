"""Annual aggregate winners ingest from the Datos Abiertos portal.

The strong version of tarea 5 needs per-sorteo winner counts by category;
those are NOT exposed by Lotería Nacional's site as static URLs (see the
feasibility note in melate-stats-spec.md §13). What IS available is the
annual aggregate `GanadoresSorteos.xlsx`, which gives total winners
per game per year, 2015–latest.

Combined with the prize structure (which lets us compute P(any prize)
per ticket analytically) and the per-year sorteo counts from the DB,
this is enough to back out the average number of tickets sold per
sorteo for each year, and from there to test the rollover excess
against a *calibrated* Poisson null instead of the v1 grid-over-N.
"""
from __future__ import annotations

import os
from math import comb
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd


DATOS_URL = "https://www.loterianacional.gob.mx/DatosAbiertos/GanadoresSorteos"


PRODUCT_LABELS_IN_XLSX: dict[str, str] = {
    # Map our internal product slug → the row label used in the XLSX.
    "melate":       "MELATE",
    "revancha":     "REVANCHA",
    "revanchita":   "REVANCHITA",
    "retro":        "MELATE RETRO",
}


def _datos_dir() -> Path:
    override = os.environ.get("MELATE_DATOS_DIR")
    if override:
        d = Path(override)
    else:
        d = Path.home() / ".melate" / "datos_abiertos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _local_xlsx_path() -> Path:
    return _datos_dir() / "GanadoresSorteos.xlsx"


def download_annual_winners_xlsx(*, force: bool = False) -> Path:
    """Download GanadoresSorteos.xlsx to the local cache. Returns the path.

    Refreshes only if `force=True` or the local file is missing.
    """
    path = _local_xlsx_path()
    if path.exists() and not force:
        return path
    # urlretrieve already follows redirects via the default opener.
    urlretrieve(DATOS_URL, path)
    return path


def load_annual_winners(*, force_download: bool = False) -> pd.DataFrame:
    """Parse the GanadoresSorteos XLSX into a long DataFrame.

    Columns: product (internal slug), year (int), winners (int).
    Only the 4 lottery products are returned; rows for the other games
    in the same XLSX are filtered out.
    """
    path = download_annual_winners_xlsx(force=force_download)
    raw = pd.read_excel(path, sheet_name=0, header=None)

    # Find the "AÑO" row to locate the column layout.
    año_row_idx = raw.index[raw.iloc[:, 0] == "AÑO"]
    if len(año_row_idx) == 0:
        raise RuntimeError(
            "GanadoresSorteos.xlsx layout changed: no 'AÑO' header found"
        )
    año_row = raw.iloc[año_row_idx[0]]
    year_cols = []
    for j, v in enumerate(año_row):
        try:
            yv = int(v)
        except (ValueError, TypeError):
            continue
        if 2000 <= yv <= 2100:
            year_cols.append((j, yv))
    if not year_cols:
        raise RuntimeError("no year columns parseable from 'AÑO' row")

    rows = []
    for product, label in PRODUCT_LABELS_IN_XLSX.items():
        match = raw.index[raw.iloc[:, 0] == label]
        if len(match) == 0:
            continue
        product_row = raw.iloc[match[0]]
        for j, year in year_cols:
            v = product_row.iloc[j]
            if pd.isna(v):
                continue
            try:
                winners = int(v)
            except (ValueError, TypeError):
                continue
            rows.append({"product": product, "year": year, "winners": winners})

    return pd.DataFrame(rows)


def p_any_win_per_ticket(
    *,
    range_: int,
    n_balls: int,
    has_additional: bool,
) -> float:
    """Analytical probability that a single ticket wins any prize.

    Per the published prize structures (see screenshot in spec):
      - Melate (6/56, +adic): any prize for ≥2 main matched.
      - Revancha (6/56): any prize for ≥2 main matched.
      - Revanchita (6/56): only "best score across all players" — no
        ticket-level probability; we approximate with the same P(≥2 main).
      - Retro (6/39, +adic): the minimum paying category is
        "1 main + adicional", so P(win) = P(≥3 main) + P(2 main, +adic)
        + P(1 main, +adic).
    """
    N = range_
    K = n_balls  # main balls drawn
    n = n_balls  # balls picked by the player

    def p_k_main(k: int) -> float:
        if k < 0 or k > min(K, n):
            return 0.0
        return comb(K, k) * comb(N - K, n - k) / comb(N, n)

    if not has_additional:
        # Melate / Revancha / Revanchita rule: win if ≥2 main.
        return sum(p_k_main(k) for k in range(2, n + 1))

    if range_ == 39 and n_balls == 6:
        # Retro: pays from "1 main + adicional" upward.
        # Adicional drawn from the N - K = 33 non-main balls. Player has
        # n - k non-main picks; probability one of them = adicional is
        # (n - k) / (N - K).
        p = 0.0
        for k in range(0, n + 1):
            pk = p_k_main(k)
            non_main_picks = n - k
            p_adic = non_main_picks / (N - K) if (N - K) > 0 else 0.0
            if k >= 3:
                p += pk                 # any ≥3 main wins regardless of adicional
            elif k == 2:
                p += pk * p_adic         # 2 main + adicional
            elif k == 1:
                p += pk * p_adic         # 1 main + adicional
        return p

    # Default (Melate / Retro-shape but range=56): win if ≥2 main.
    # (Melate technically has additional categories that include +adic at
    # lower main counts, but the cutoff for "any prize" still starts at
    # 2 main — additional just multiplies the prize tier.)
    return sum(p_k_main(k) for k in range(2, n + 1))
