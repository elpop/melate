from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from stats.report import build_report


def test_build_report_writes_markdown_and_figures(tmp_path):
    fig = plt.figure()
    plt.plot([1, 2, 3])
    results = {
        "product_name": "Melate",
        "sections": [
            {"title": "Chi-square (r1..r6)",
             "summary": "stat=55.0, dof=55, p=0.45",
             "figure": fig,
             "expected_per_spec": "p > 0.05 (no rechazar uniformidad)",
             "matches_expectation": True},
        ],
    }
    out = build_report(results, tmp_path)
    assert out == tmp_path / "report.md"
    assert out.exists()
    body = out.read_text()
    assert "Melate" in body
    assert "Chi-square (r1..r6)" in body
    assert "stat=55.0" in body
    assert "![Chi-square" in body or "![chi-square" in body or "(figs/" in body
    figs = list((tmp_path / "figs").glob("*.png"))
    assert len(figs) == 1


def test_build_report_flags_mismatch_with_attention_banner(tmp_path):
    fig = plt.figure()
    plt.plot([1])
    results = {
        "product_name": "Melate",
        "sections": [
            {"title": "Backtest",
             "summary": "weight_rate=0.99 vs baseline=0.64 (p=1e-9)",
             "figure": fig,
             "expected_per_spec": "weight ≈ baseline (no rechazar)",
             "matches_expectation": False},
        ],
    }
    out = build_report(results, tmp_path)
    body = out.read_text()
    assert "ATENCIÓN" in body or "ATTENTION" in body
    assert "Backtest" in body
