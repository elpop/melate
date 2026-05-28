"""CLI entry point: python -m stats --product X --analyses Y,Z --output DIR."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pandas as pd

from stats.db import load_draws
from stats.fairness import chi_square_uniformity, bayesian_fairness, correct_pvalues
from stats.backtest import weight_walkforward
from stats.rollover import derive_jackpot_won
from stats.behavior import rollover_excess
from stats.report import build_report


ANALYSES = {"chi2", "bayes", "backtest", "behavior", "all"}


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
        requested = {"chi2", "bayes", "backtest", "behavior"}

    sections = []
    if "chi2" in requested:
        sections.append(_run_chi2(data))
        if data.has_additional:
            sections.append(_run_chi2_r7(data))
    _apply_bonferroni_to_chi2_sections(sections)
    if "bayes" in requested:
        sections.append(_run_bayes(data))
    if "backtest" in requested:
        sections.append(_run_backtest(data))
    if "behavior" in requested:
        sections.append(_run_behavior(data))

    results = {"product_name": data.product_name, "sections": sections}
    out = build_report(results, args.output)
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
