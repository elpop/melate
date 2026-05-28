from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_full_pipeline_on_real_melate(tmp_path, real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    out = tmp_path / "report"
    result = subprocess.run(
        [sys.executable, "-m", "stats",
         "--product", "melate",
         "--analyses", "all",
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"e2e failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    report = out / "report.md"
    assert report.exists()
    body = report.read_text()
    # All three baldes present
    assert "Chi-square" in body
    assert "Backtest" in body
    assert "Rollover excess" in body
    print(f"\n--- report.md ---\n{body[:2000]}\n--- end ---")
