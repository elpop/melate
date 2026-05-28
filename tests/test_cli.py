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
