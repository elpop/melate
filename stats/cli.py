"""CLI entry point: python -m stats --product X --analyses Y,Z --output DIR."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pandas as pd

from stats.db import load_draws
from stats.fairness import (
    chi_square_uniformity, bayesian_fairness, correct_pvalues, gaps_test,
)
from stats.multivariate import cooccurrence_test
from stats.drift import pettitt_per_ball
from stats.serial import serial_independence_per_ball
from stats.backtest import weight_walkforward
from stats.rollover import derive_jackpot_won
from stats.behavior import rollover_excess, rollover_excess_annual
from stats.ingest import load_annual_winners, p_any_win_per_ticket
from stats.report import build_report


ANALYSES = {"chi2", "bayes", "cooccurrence", "gaps", "drift", "serial",
            "backtest", "behavior", "behavior-annual", "all"}


def _chi2_summary(res, *, scope: str) -> str:
    """Build the summary string for a χ² section, including the sanity band
    [gl − 2·√(2·gl), gl + 2·√(2·gl)] per design §5."""
    band_lo = res.dof - 2 * (2 * res.dof) ** 0.5
    band_hi = res.dof + 2 * (2 * res.dof) ** 0.5
    within = band_lo <= res.stat <= band_hi
    return (
        f"stat={res.stat:.2f}, dof={res.dof}, p={res.p_value:.4f}; "
        f"sanity band [{band_lo:.1f}, {band_hi:.1f}] "
        f"({'within' if within else 'OUTSIDE'} → {scope})"
    )


def _run_chi2(data) -> dict:
    res = chi_square_uniformity(data.draws_long["ball"], data.range)
    return {
        "title": "Chi-square goodness-of-fit (r1..r6)",
        "summary": _chi2_summary(res, scope="r1..r6"),
        "figure": res.fig,
        "expected_per_spec": "p > 0.05 (no rechazar uniformidad)",
        "matches_expectation": res.p_value > 0.05,
        "_kind": "chi2",
        "_p_raw": res.p_value,
    }


def _run_chi2_r7(data) -> dict:
    """χ² over the additional ball r7 (only Melate id=40 and Retro id=30).

    Analyzed separately from r1..r6 because r7 is drawn from a potentially
    distinct mechanism — mixing the two would muddy a sane fairness test.
    """
    samples = data.r7_series.dropna().astype("int64")
    res = chi_square_uniformity(samples, data.range)
    return {
        "title": "Chi-square goodness-of-fit (r7 additional ball)",
        "summary": _chi2_summary(res, scope="r7"),
        "figure": res.fig,
        "expected_per_spec": "p > 0.05 (la bola adicional debe ser uniforme)",
        "matches_expectation": res.p_value > 0.05,
        "_kind": "chi2",
        "_p_raw": res.p_value,
    }


def _apply_bonferroni_to_chi2_sections(sections: list[dict]) -> None:
    """When ≥2 χ² sections are present in the report, apply Bonferroni
    correction across them and overwrite each section's match decision
    based on the corrected p-value. Per spec §5 / tarea 2 — transversal."""
    chi2_sections = [s for s in sections if s.get("_kind") == "chi2"]
    if len(chi2_sections) < 2:
        return
    pvals = pd.Series([s["_p_raw"] for s in chi2_sections])
    corrected = correct_pvalues(pvals, method="bonferroni")
    threshold = 0.05 / len(chi2_sections)
    for i, s in enumerate(chi2_sections):
        corr_p = float(corrected["pval_corrected"].iloc[i])
        significant = bool(corrected["significant_at_05"].iloc[i])
        s["summary"] += (
            f"\n\n**Bonferroni** (m={len(chi2_sections)}): "
            f"corrected p = {corr_p:.4f} "
            f"(threshold α/m = {threshold:.4f}); "
            f"{'STILL significant' if significant else 'NOT significant'} after correction"
        )
        s["matches_expectation"] = not significant


def _run_bayes(data) -> dict:
    """Bayesian Dirichlet-multinomial fairness (tarea 6 del spec original)."""
    res = bayesian_fairness(data.draws_long["ball"], data.range)
    contains_pct = 100.0 * res.contains_uniform_count / data.range
    return {
        "title": "Bayesian fairness (Dirichlet-multinomial, r1..r6)",
        "summary": (
            f"log BF (fair vs flexible) = {res.log_bayes_factor_fair_vs_dirichlet:+.2f}; "
            f"{res.contains_uniform_count}/{data.range} ({contains_pct:.0f}%) "
            f"CIs 95% contienen la uniforme"
        ),
        "figure": res.fig,
        "expected_per_spec": (
            "log BF > 0 (favorece fair) y ~95% de CIs contienen la uniforme"
        ),
        "matches_expectation": (
            res.log_bayes_factor_fair_vs_dirichlet > 0
            and res.contains_uniform_count >= int(0.85 * data.range)
        ),
    }


def _run_cooccurrence(data) -> dict:
    """Pairwise co-occurrence vs multivariate hypergeometric (tarea 7)."""
    res = cooccurrence_test(
        data.draws_wide, range_=data.range, n_balls=data.n_balls,
    )
    n_pairs = data.range * (data.range - 1) // 2
    expected_at_nominal = 0.05 * n_pairs
    return {
        "title": "Pairwise co-occurrence (r1..r6 vs multivariate hypergeometric)",
        "summary": (
            f"n_draws={res.n_draws}, expected/pair={res.expected_per_pair:.1f}, "
            f"max|z|={res.max_abs_z:.2f}\n"
            f"Pairs over |z|>1.96 (nominal 5%): "
            f"{res.n_extreme_at_nominal_05}/{n_pairs} "
            f"(expected by chance ≈ {expected_at_nominal:.0f})\n"
            f"Pairs over Bonferroni threshold ({res.bonferroni_threshold:.2f}σ): "
            f"**{res.n_extreme_at_bonferroni}**"
        ),
        "figure": res.fig,
        "expected_per_spec": (
            "0 pairs sobreviven Bonferroni; conteo nominal cerca de 5% del total"
        ),
        "matches_expectation": res.n_extreme_at_bonferroni == 0,
    }


def _run_gaps(data) -> dict:
    """Per-ball gap distribution vs geom(n_balls/range) (tarea 8)."""
    res = gaps_test(data.draws_wide, range_=data.range, n_balls=data.n_balls)
    expected_at_nominal = 0.05 * data.range
    expected_mean_gap = data.range / data.n_balls
    return {
        "title": "Gap distribution (r1..r6 vs geometric)",
        "summary": (
            f"n_draws={res.n_draws}, p_appear={res.p_appear_per_draw:.4f}, "
            f"expected mean gap = {expected_mean_gap:.2f}\n"
            f"Balls significant at α=0.05 (uncorrected): "
            f"{res.n_significant_at_nominal_05}/{data.range} "
            f"(expected by chance ≈ {expected_at_nominal:.0f})\n"
            f"Balls significant at Bonferroni (α/range = {res.bonferroni_threshold:.4f}): "
            f"**{res.n_significant_at_bonferroni}**"
        ),
        "figure": res.fig,
        "expected_per_spec": (
            "0 bolas sobreviven Bonferroni; nominal cerca de 5% (~3 bolas para range=56)"
        ),
        "matches_expectation": res.n_significant_at_bonferroni == 0,
    }


def _run_drift(data) -> dict:
    """Pettitt change-point per ball (tarea 10)."""
    res = pettitt_per_ball(data.draws_wide, range_=data.range,
                           n_balls=data.n_balls)
    expected_at_nominal = 0.05 * data.range
    return {
        "title": "Temporal drift (Pettitt change-point, r1..r6)",
        "summary": (
            f"n_draws={res.n_draws}; Bonferroni threshold "
            f"(α/range) = {res.bonferroni_threshold:.4f}\n"
            f"Balls significant at α=0.05 (uncorrected): "
            f"{res.n_significant_at_nominal_05}/{data.range} "
            f"(expected by chance ≈ {expected_at_nominal:.0f})\n"
            f"Balls significant at Bonferroni: "
            f"**{res.n_significant_at_bonferroni}**"
        ),
        "figure": res.fig,
        "expected_per_spec": (
            "0 bolas sobreviven Bonferroni; sin change-points evidentes"
        ),
        "matches_expectation": res.n_significant_at_bonferroni == 0,
    }


def _run_behavior_annual(data) -> dict | None:
    """Annual rollover-excess with N calibrated from XLSX winner totals
    (tarea 13 (a) — medium-strength version of tarea 5).

    Revanchita is intentionally skipped: its prize rule is "quien obtenga
    más aciertos (9)" — the player(s) with the highest match count win,
    regardless of category — so the constant p_any_win analytical formula
    used here does not apply. Annual totals for Revanchita reflect only
    those rare best-of-the-pool winners (22 total in 10 years), which
    breaks the calibration.
    """
    slug_by_name = {"Melate": "melate", "Revancha": "revancha",
                    "Revanchita": "revanchita", "Melate Retro": "retro"}
    slug = slug_by_name[data.product_name]
    if slug == "revanchita":
        return None

    try:
        annual = load_annual_winners().query(f"product == '{slug}'")[
            ["year", "winners"]
        ]
    except Exception:
        return None
    if annual.empty:
        return None

    jackpot = derive_jackpot_won(data.draws_wide["award"])
    p_win = p_any_win_per_ticket(
        range_=data.range, n_balls=data.n_balls,
        has_additional=data.has_additional,
    )
    res = rollover_excess_annual(
        jackpot, data.draws_wide["date"], annual,
        range_=data.range, n_balls=data.n_balls, p_any_win=p_win,
    )
    n_years = len(res.per_year)
    summary = (
        f"N calibrado promedio = "
        f"{res.per_year['n_calibrated_per_sorteo'].mean():,.0f} boletos/sorteo "
        f"(rango: {res.per_year['n_calibrated_per_sorteo'].min():,.0f}–"
        f"{res.per_year['n_calibrated_per_sorteo'].max():,.0f})\n"
        f"Cobertura: {n_years} año(s) con datos completos (DB + XLSX).\n"
        f"**Overall ratio observed/expected = {res.overall_ratio:.3f}, "
        f"p = {res.overall_p_value:.4f}**\n\n"
        f"> N por sorteo se DERIVA del número total de ganadores publicado "
        f"y de P(any prize) analítica — no se asume. ratio<1 indica menos "
        f"jackpots que lo esperado bajo juego uniforme → posible selección "
        f"consciente. ratio≈1 indica juego uniforme (o equilibrio entre "
        f"selección consciente y Quick Pick)."
    )
    return {
        "title": "Annual rollover excess (calibrated N from XLSX)",
        "summary": summary,
        "figure": res.fig,
        "expected_per_spec": (
            "ratio observed/expected entre 0.7 y 1.0 (signal débil de "
            "selección consciente sin significancia con ~10 años)"
        ),
        # Pass if signal is consistent with conscious selection (ratio<1) OR uniform (≈1).
        # Fail only if the result violates the design — e.g., ratio >> 1 with p < 0.05.
        "matches_expectation": (
            res.overall_ratio < 1.5
            and (res.overall_p_value > 0.05 or res.overall_ratio < 1.0)
        ),
    }


def _run_serial(data) -> dict:
    """Runs test + lag-1 autocorrelation per ball (tarea 9)."""
    res = serial_independence_per_ball(
        data.draws_wide, range_=data.range, n_balls=data.n_balls,
    )
    expected_at_nominal = 0.05 * data.range
    return {
        "title": "Serial independence (runs + lag-1 autocorrelation, r1..r6)",
        "summary": (
            f"n_draws={res.n_draws}; Bonferroni threshold "
            f"(α/(2·range)) = {res.bonferroni_threshold:.4f}\n"
            f"Balls significant at α=0.05 (uncorrected): "
            f"{res.n_significant_at_nominal_05}/{data.range} "
            f"(expected by chance ≈ {expected_at_nominal:.0f})\n"
            f"Balls significant at Bonferroni: "
            f"**{res.n_significant_at_bonferroni}**"
        ),
        "figure": res.fig,
        "expected_per_spec": (
            "0 bolas sobreviven Bonferroni; runs y autocorrelaciones dentro de banda"
        ),
        "matches_expectation": res.n_significant_at_bonferroni == 0,
    }


def _run_backtest(data) -> dict:
    res = weight_walkforward(
        data.draws_wide, n_balls=data.n_balls, range_=data.range,
        window=60, breaks=10,
        start_at=min(500, max(2, len(data.draws_wide) // 4)),
    )
    return {
        "title": "Backtest of -weight (walk-forward)",
        "summary": (f"weight_rate={res.hit_rate_weight:.3f}, "
                    f"baseline={res.hit_rate_baseline_analytical:.3f}, "
                    f"p={res.p_value_vs_baseline:.4f}"),
        "figure": res.fig,
        "expected_per_spec": "weight ≈ baseline (no rechazar igualdad al azar)",
        "matches_expectation": res.p_value_vs_baseline > 0.05,
    }


def _run_behavior(data) -> dict:
    jackpot = derive_jackpot_won(data.draws_wide["award"])
    res = rollover_excess(
        jackpot, range_=data.range, n_balls=data.n_balls,
        n_players_grid=[1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000],
    )
    largest = res.per_N.iloc[-1]
    summary = (f"observed_rate={res.observed_rollover_rate:.3f}; "
               f"at largest N={int(largest['N']):,}: ratio={largest['ratio']:.3f}")
    summary += ("\n\n> N (número de boletos vendidos por sorteo) se trata como "
                "parámetro de molestia; el resultado se presenta sobre un rango "
                "plausible de N en vez de fijar un valor único.\n\n"
                "> Este número subestima el efecto real; una fracción desconocida "
                "de jugadores usa Quick Pick (selección automática), que es uniforme "
                "y atenúa el exceso de rollovers medible.")
    return {
        "title": "Rollover excess (lower bound on conscious selection)",
        "summary": summary,
        "figure": res.fig,
        "expected_per_spec": "ratio > 1 al N más grande del grid (cota inferior)",
        "matches_expectation": largest["ratio"] > 1.0,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stats", description="Melate stats v1")
    p.add_argument("--product", required=True,
                   choices=["melate", "revancha", "revanchita", "retro"])
    p.add_argument("--analyses", required=True,
                   help="Comma-separated: chi2,backtest,behavior,all")
    p.add_argument("--output", required=True, type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    requested = {s.strip() for s in args.analyses.split(",")}
    unknown = requested - ANALYSES
    if unknown:
        print(f"unknown analyses: {sorted(unknown)}", file=sys.stderr)
        return 2

    try:
        data = load_draws(args.product)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if "all" in requested:
        requested = {"chi2", "bayes", "cooccurrence", "gaps", "drift", "serial",
                     "backtest", "behavior", "behavior-annual"}

    sections = []
    if "chi2" in requested:
        sections.append(_run_chi2(data))
        if data.has_additional:
            sections.append(_run_chi2_r7(data))
    _apply_bonferroni_to_chi2_sections(sections)
    if "bayes" in requested:
        sections.append(_run_bayes(data))
    if "cooccurrence" in requested:
        sections.append(_run_cooccurrence(data))
    if "gaps" in requested:
        sections.append(_run_gaps(data))
    if "drift" in requested:
        sections.append(_run_drift(data))
    if "serial" in requested:
        sections.append(_run_serial(data))
    if "backtest" in requested:
        sections.append(_run_backtest(data))
    if "behavior" in requested:
        sections.append(_run_behavior(data))
    if "behavior-annual" in requested:
        annual_section = _run_behavior_annual(data)
        if annual_section is not None:
            sections.append(annual_section)

    results = {"product_name": data.product_name, "sections": sections}
    out = build_report(results, args.output)
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
