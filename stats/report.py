"""Assemble Markdown + figures report from analysis results."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build_report(results: dict[str, Any], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    figs_dir = output_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    sections = results.get("sections", [])
    mismatches = [s for s in sections if not s.get("matches_expectation", True)]

    lines: list[str] = []
    lines.append(f"# Melate stats report — {results.get('product_name', '')}")
    lines.append("")
    if mismatches:
        lines.append("> ## ⚠️ ATENCIÓN")
        lines.append(">")
        lines.append("> Los siguientes resultados contradicen lo esperado por el spec. "
                     "Tratar primero como **posible bug**, no como hallazgo, hasta auditar:")
        for s in mismatches:
            lines.append(f"> - **{s['title']}**: {s['summary']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    for s in sections:
        title = s["title"]
        slug = _slug(title)
        fig_path = figs_dir / f"{slug}.png"
        s["figure"].savefig(fig_path, dpi=120)
        plt.close(s["figure"])
        lines.append(f"## {title}")
        lines.append("")
        lines.append(s["summary"])
        lines.append("")
        lines.append(f"**Esperado por spec:** {s.get('expected_per_spec', '—')}")
        lines.append(f"**Coincide:** {'✅' if s.get('matches_expectation', True) else '❌'}")
        lines.append("")
        lines.append(f"![{title}](figs/{slug}.png)")
        lines.append("")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines))
    return report_path
