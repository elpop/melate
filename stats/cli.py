"""CLI entry point: python -m stats --product X --analyses Y,Z --output DIR."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from stats.db import load_draws
from stats.fairness import chi_square_uniformity, bayesian_fairness
from stats.backtest import weight_walkforward
from stats.rollover import derive_jackpot_won
from stats.behavior import rollover_excess
from stats.report import build_report


ANALYSES = {"chi2", "bayes", "backtest", "rollover", "behavior", "all"}


def _run_chi2(data) -> dict:
    res = chi_square_uniformity(data.draws_long["ball"], data.range)
    return {
        "title": "Chi-square goodness-of-fit (r1..r6)",
        "summary": f"stat={res.stat:.2f}, dof={res.dof}, p={res.p_value:.4f}",
        "figure": res.fig,
        "expected_per_spec": "p > 0.05 (no rechazar uniformidad)",
        "matches_expectation": res.p_value > 0.05,
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
        "summary": f"stat={res.stat:.2f}, dof={res.dof}, p={res.p_value:.4f}",
        "figure": res.fig,
        "expected_per_spec": "p > 0.05 (la bola adicional debe ser uniforme)",
        "matches_expectation": res.p_value > 0.05,
    }


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
               f"at largest N={largest['N']:,}: ratio={largest['ratio']:.3f}")
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
