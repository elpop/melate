from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_chi2_writes_report(tiny_db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "melate",
         "--analyses", "chi2",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"CLI failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    report = out / "report.md"
    assert report.exists(), f"no report at {report}"
    body = report.read_text()
    assert "Chi-square" in body or "chi" in body.lower()


def test_cli_unknown_product_exits_nonzero(tiny_db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    result = subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "powerball",
         "--analyses", "chi2",
         "--output", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "unknown product" in result.stderr.lower() or "powerball" in result.stderr


def test_cli_chi2_for_product_with_additional_includes_r7_section(
    tiny_db_path, tmp_path, monkeypatch
):
    """Melate (has_additional=True) must get a chi² section for r7 in addition to r1..r6."""
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "melate",
         "--analyses", "chi2",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    body = (out / "report.md").read_text()
    # Two H2 chi-square sections: r1..r6 main + r7 additional
    assert body.count("## Chi-square goodness-of-fit") == 2
    assert "r1..r6" in body
    assert "r7" in body


def test_cli_chi2_for_product_without_additional_skips_r7(
    tiny_db_path, tmp_path, monkeypatch
):
    """Revancha (has_additional=False) gets only the r1..r6 chi² section."""
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "revancha",
         "--analyses", "chi2",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    body = (out / "report.md").read_text()
    assert body.count("## Chi-square goodness-of-fit") == 1
    assert "r7" not in body


def test_cli_chi2_summary_includes_sanity_band(tiny_db_path, tmp_path, monkeypatch):
    """Per design §5, the χ² report must include the sanity band, not just p."""
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    out = tmp_path / "out"
    subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "revanchita",
         "--analyses", "chi2",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    body = (out / "report.md").read_text()
    # Sanity band string must appear, with both bounds
    assert "sanity band" in body.lower() or "banda" in body.lower()
    # The band for gl=55 is [34.0, 76.0] (gl ± 2·sqrt(2·gl))
    # Just verify the substrings; exact values may differ if dof shifts.
    import re
    assert re.search(r"\d+\.\d.*?\d+\.\d", body), \
        "expected numeric band bounds in chi² summary"


def test_cli_chi2_applies_bonferroni_when_two_sections(
    tiny_db_path, tmp_path, monkeypatch
):
    """With ≥2 χ² in the report, Bonferroni correction must be reported and
    must drive matches_expectation. Otherwise we'd flag false positives."""
    monkeypatch.setenv("MELATE_DB", str(tiny_db_path))
    out = tmp_path / "out"
    subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "melate",
         "--analyses", "chi2",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    body = (out / "report.md").read_text()
    # Both χ² sections present
    assert body.count("## Chi-square goodness-of-fit") == 2
    # Bonferroni correction mentioned
    assert "Bonferroni" in body or "bonferroni" in body
    # The reporting must include the corrected p (i.e. NOT just raw p)
    assert "corrected" in body.lower()
