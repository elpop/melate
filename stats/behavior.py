"""Tarea 5 — conscious-selection lower bound via rollover excess."""
from __future__ import annotations

from dataclasses import dataclass
from math import comb

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


@dataclass
class RolloverExcessResult:
    observed_rollover_rate: float
    per_N: pd.DataFrame  # N, expected_rate_poisson, ratio, p_value, ci_lo, ci_hi
    fig: Figure


@dataclass
class AnnualRolloverExcessResult:
    """Calibrated-N version: N estimated from annual winner counts and the
    analytical P(any prize) per ticket; no nuisance grid."""
    per_year: pd.DataFrame   # year, n_sorteos, n_jackpots, total_winners,
                              # n_calibrated_per_sorteo, expected_jackpot_rate,
                              # observed_jackpot_rate, ratio, p_value
    overall_ratio: float
    overall_p_value: float
    fig: Figure


def rollover_excess(
    jackpot_df: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    n_players_grid,
) -> RolloverExcessResult:
    """Compare observed rollover rate against Poisson-uniform predictions for a grid of N."""
    # rollover ⇔ NOT won. dropna keeps only resolved sorteos (last sorteo
    # and ambiguous ones are NA-marked and excluded). astype(bool) collapses
    # the nullable BooleanDtype back to numpy bool so ~ works as expected.
    won = jackpot_df["jackpot_won"].dropna().astype(bool)
    rollovers = int((~won).sum())
    n_obs = len(won)
    observed_rate = rollovers / n_obs

    p_jackpot = 1.0 / comb(range_, n_balls)

    rows = []
    for N in n_players_grid:
        expected_rate = float(np.exp(-N * p_jackpot))
        ratio = observed_rate / expected_rate if expected_rate > 0 else float("inf")
        # Binomial test: observed rollovers ~ Binomial(n_obs, expected_rate)
        binom = stats.binomtest(rollovers, n_obs, expected_rate, alternative="two-sided")
        p_value = binom.pvalue
        ci_lo, ci_hi = binom.proportion_ci(confidence_level=0.95)
        rows.append({
            "N": int(N),
            "expected_rate_poisson": expected_rate,
            "ratio": ratio,
            "p_value": float(p_value),
            "ci_lo": float(ci_lo),
            "ci_hi": float(ci_hi),
        })

    per_N = pd.DataFrame(rows)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(per_N["N"], per_N["ratio"], "o-", color="steelblue", label="observed/expected")
    ax.axhline(1.0, color="red", linestyle="--", label="ratio=1 (uniform null)")
    ax.set_xscale("log")
    ax.set_xlabel("N (assumed tickets per draw)")
    ax.set_ylabel("rollover rate ratio (observed / expected)")
    ax.set_title(f"Observed rollover rate = {observed_rate:.3f}")
    ax.legend()
    fig.tight_layout()

    return RolloverExcessResult(
        observed_rollover_rate=observed_rate,
        per_N=per_N,
        fig=fig,
    )


def rollover_excess_annual(
    jackpot_df: pd.DataFrame,
    dates: pd.Series,
    annual_winners: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    p_any_win: float,
) -> AnnualRolloverExcessResult:
    """Annual-calibrated version of the rollover excess test.

    For each year:
      - Read total winners from the published XLSX (annual_winners).
      - Count n_sorteos in our DB for that year.
      - Back out the average N tickets per sorteo:
          N_year = winners_year / (p_any_win × n_sorteos_year).
      - Compute expected per-sorteo jackpot rate under uniform play:
          E[jackpot rate] = 1 − exp(−N_year × p_jackpot).
      - Compare to the observed jackpot rate from F0.5.

    Ratio_year = observed_jackpot_rate / expected_jackpot_rate.
    Under uniform play, ratio ≈ 1. Conscious selection inflates the
    rollover rate (= 1 − jackpot rate), which DEFLATES this ratio below 1.
    """
    # Align dates with jackpot_df (both come from sorted draws_wide).
    j = jackpot_df.copy().reset_index(drop=True)
    j["year"] = pd.to_datetime(dates.reset_index(drop=True)).dt.year

    p_jackpot = 1.0 / comb(range_, n_balls)

    rows = []
    for year, grp in j.groupby("year"):
        resolved = grp.dropna(subset=["jackpot_won"])
        n_sorteos = len(resolved)
        if n_sorteos == 0:
            continue
        n_jackpots = int(resolved["jackpot_won"].astype(bool).sum())

        winners_lookup = annual_winners[annual_winners["year"] == int(year)]
        if winners_lookup.empty:
            continue
        total_winners = int(winners_lookup["winners"].iloc[0])

        n_per_sorteo = total_winners / (p_any_win * n_sorteos)
        expected_rate = 1.0 - float(np.exp(-n_per_sorteo * p_jackpot))
        observed_rate = n_jackpots / n_sorteos
        ratio = observed_rate / expected_rate if expected_rate > 0 else float("nan")

        # Two-sided binomial test on observed jackpot count vs the calibrated rate.
        try:
            p_value = float(
                stats.binomtest(n_jackpots, n_sorteos, expected_rate,
                                alternative="two-sided").pvalue
            )
        except ValueError:
            p_value = float("nan")
        rows.append({
            "year": int(year),
            "n_sorteos": n_sorteos,
            "n_jackpots": n_jackpots,
            "total_winners": total_winners,
            "n_calibrated_per_sorteo": float(n_per_sorteo),
            "expected_jackpot_rate": expected_rate,
            "observed_jackpot_rate": observed_rate,
            "ratio": ratio,
            "p_value": p_value,
        })

    per_year = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)

    # Overall: sum jackpots, sum expected jackpots; two-sided binomial.
    total_jackpots = int(per_year["n_jackpots"].sum()) if not per_year.empty else 0
    expected_jackpots = float(
        (per_year["expected_jackpot_rate"] * per_year["n_sorteos"]).sum()
    ) if not per_year.empty else 0.0
    total_sorteos = int(per_year["n_sorteos"].sum()) if not per_year.empty else 0
    if total_sorteos > 0 and expected_jackpots > 0:
        overall_rate_expected = expected_jackpots / total_sorteos
        overall_ratio = (total_jackpots / total_sorteos) / overall_rate_expected
        overall_p = float(
            stats.binomtest(total_jackpots, total_sorteos, overall_rate_expected,
                            alternative="two-sided").pvalue
        )
    else:
        overall_ratio = float("nan")
        overall_p = float("nan")

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 4))
    if not per_year.empty:
        ax.plot(per_year["year"], per_year["ratio"], "o-",
                color="steelblue", label="ratio observed/expected (per year)")
        ax.axhline(1.0, color="red", linestyle="--", label="uniform null (ratio=1)")
        ax.axhline(overall_ratio, color="green", linestyle=":",
                   label=f"overall ratio = {overall_ratio:.3f}")
        # Sanity annotation: log scale would flatten 0→large extreme; linear is fine for ~0.5–2.
        ax.set_xlabel("year")
        ax.set_ylabel("jackpot rate ratio (observed / expected under calibrated N)")
        ax.set_title(
            f"Annual rollover-excess (calibrated N)  "
            f"overall ratio={overall_ratio:.3f}, p={overall_p:.4f}"
        )
        ax.legend()
    fig.tight_layout()

    return AnnualRolloverExcessResult(
        per_year=per_year,
        overall_ratio=overall_ratio,
        overall_p_value=overall_p,
        fig=fig,
    )
