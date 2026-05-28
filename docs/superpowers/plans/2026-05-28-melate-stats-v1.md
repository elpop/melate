# Melate Stats v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** build the `stats/` Python module that runs statistical inference on the Melate SQLite history, delivering the v1 narrative: fairness (χ² + Bonferroni + Monte Carlo) → backtest of the `-weight` feature → rollover-based conscious-selection bound, with a Markdown + figures report.

**Architecture:** modular strict, one concern per file, pure functions per analysis. Read-only over `~/.melate/melate.db`. TDD per module against an in-memory synthetic SQLite fixture; statistical-property assertions go to integration tests gated by `@pytest.mark.integration` against the real DB.

**Tech Stack:** Python 3.11+, `pandas`, `numpy`, `scipy.stats`, `statsmodels`, `matplotlib`. `pytest` for tests. `sqlite3` stdlib for DB access.

**Source of truth for contracts:** [`docs/superpowers/specs/2026-05-28-melate-stats-design.md`](../specs/2026-05-28-melate-stats-design.md). When this plan says "per design §X", check that section.

**Checkpoints (parar y mostrar al usuario antes de seguir):**
- CP1 after Task 3 — F0 verde, conteos coinciden con `SELECT COUNT(*) FROM results`.
- CP2 after Task 6 — Tier 1 (χ² + corrección + Monte Carlo) verde sobre Melate real.
- CP3 after Task 9 — backtest del `-weight` verde, assert anti-leakage pasa.
- CP4 after Task 12 — F0.5 + tarea 5 verdes, los tres baldes integrados.
- v1 done after Task 15.

---

## File Structure

```
melate/
├── pyproject.toml                  # NEW
├── .gitignore                      # MODIFIED
├── stats/                          # NEW package
│   ├── __init__.py
│   ├── db.py
│   ├── rollover.py
│   ├── fairness.py
│   ├── backtest.py
│   ├── behavior.py
│   ├── report.py
│   └── cli.py
└── tests/                          # NEW
    ├── __init__.py
    ├── conftest.py
    ├── test_db.py
    ├── test_rollover.py
    ├── test_fairness.py
    ├── test_backtest.py
    ├── test_behavior.py
    └── test_cli.py
```

Each `stats/*.py` is small and focused. Tests one-to-one with modules.

---

## Task 0: Project setup (pyproject.toml, package skeleton, fixtures)

**Files:**
- Create: `pyproject.toml`
- Create: `stats/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "melate-stats"
version = "0.1.0"
description = "Statistical inference module over the Melate lottery history"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "numpy>=1.24",
    "scipy>=1.11",
    "statsmodels>=0.14",
    "matplotlib>=3.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
]

[project.scripts]
melate-stats = "stats.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["stats*"]

[tool.pytest.ini_options]
markers = [
    "integration: requires populated ~/.melate/melate.db (deselect with '-m \"not integration\"')",
]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p stats tests
touch stats/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create `tests/conftest.py` with fixtures**

```python
"""Shared pytest fixtures: synthetic and real DB paths."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


PRODUCTS_SEED = [
    # (id, name, range, balls, additional, url, filename)
    (40, "Melate",       56, 6, 1, "", "Melate"),
    (41, "Revancha",     56, 6, 0, "", "Revancha"),
    (34, "Revanchita",   56, 6, 0, "", "Revanchita"),
    (30, "Melate Retro", 39, 6, 1, "", "Retro"),
]


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE products (
            id integer not null,
            name text not null,
            range integer not null,
            balls integer not null,
            additional integer not null,
            url text not null,
            filename text not null
        );
        CREATE UNIQUE INDEX un_p_id ON products(id);
        CREATE TABLE results (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            draw integer NOT NULL,
            date_time TEXT NOT NULL,
            r1 integer, r2 integer, r3 integer, r4 integer,
            r5 integer, r6 integer, r7 integer,
            award integer,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE UNIQUE INDEX un_pi_d_results ON results(product_id, draw);
        """
    )


def _seed_products(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO products(id,name,range,balls,additional,url,filename) "
        "VALUES (?,?,?,?,?,?,?)",
        PRODUCTS_SEED,
    )


def _seed_draws(conn: sqlite3.Connection, product_id: int, n_draws: int,
                range_: int, additional: int) -> None:
    """Insert n_draws synthetic draws for a product.

    r1..r6: deterministic permutation of 6 values in [1, range_] per draw.
    r7: integer in [1, range_] if additional==1, else '' (matches melate.pl:366).
    award: monotone-ish series with resets to a floor every ~15 draws.
    """
    import random

    rng = random.Random(product_id)
    floor = 30_000_000 if range_ == 56 else 5_000_000
    award = floor
    rows = []
    for k in range(1, n_draws + 1):
        balls = rng.sample(range(1, range_ + 1), 6)
        r7 = rng.randint(1, range_) if additional == 1 else ""
        if k % 15 == 0:
            award = floor  # simulated jackpot win → reset
        else:
            award += rng.randint(500_000, 3_000_000)
        rows.append((product_id, k, f"2024-01-{(k % 28) + 1:02d}",
                     *balls, r7, award))
    conn.executemany(
        "INSERT INTO results(product_id,draw,date_time,r1,r2,r3,r4,r5,r6,r7,award) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


@pytest.fixture
def tiny_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ephemeral SQLite with the real schema and ~50 synthetic draws per product.

    Scope: lógica only (parsing, normalization, edge cases). NOT statistical properties.
    """
    db_path = tmp_path / "melate.db"
    conn = sqlite3.connect(db_path)
    _create_schema(conn)
    _seed_products(conn)
    for pid, _name, range_, _balls, additional, *_ in PRODUCTS_SEED:
        _seed_draws(conn, pid, n_draws=50, range_=range_, additional=additional)
    conn.commit()
    conn.close()
    monkeypatch.setenv("MELATE_DB", str(db_path))
    return db_path


@pytest.fixture
def real_db_path() -> Path:
    """Path to the real ~/.melate/melate.db; skips if absent."""
    path = Path.home() / ".melate" / "melate.db"
    if not path.exists():
        pytest.skip("real Melate DB not present at ~/.melate/melate.db")
    return path
```

- [ ] **Step 4: Modify `.gitignore`** — append:

```
# Python
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.coverage

# Stats output
report/
```

- [ ] **Step 5: Verify pytest collects nothing and runs**

Run: `pytest -v`
Expected: `no tests ran` (no errors).

- [ ] **Step 6: Install in editable mode**

Run: `pip install -e ".[dev]"`
Expected: successful install.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml stats/ tests/ .gitignore
git commit -m "stats: project setup (pyproject, package skeleton, fixtures)"
```

---

## Task 1: F0 — `load_draws` skeleton + `DrawData` dataclass

**Files:**
- Create: `stats/db.py`
- Create: `tests/test_db.py`

**Per design §4, §5 / db.py.**

- [ ] **Step 1: Write failing test for product metadata loading**

`tests/test_db.py`:

```python
from __future__ import annotations

import pytest

from stats.db import load_draws, DrawData, DataIntegrityError


def test_load_draws_melate_returns_product_metadata(tiny_db_path):
    data = load_draws("melate")
    assert isinstance(data, DrawData)
    assert data.product_name == "Melate"
    assert data.product_id == 40
    assert data.range == 56
    assert data.n_balls == 6
    assert data.has_additional is True


def test_load_draws_revancha_metadata(tiny_db_path):
    data = load_draws("revancha")
    assert data.product_id == 41
    assert data.range == 56
    assert data.has_additional is False


def test_load_draws_retro_metadata(tiny_db_path):
    data = load_draws("retro")
    assert data.product_id == 30
    assert data.range == 39
    assert data.has_additional is True


def test_load_draws_unknown_product_raises(tiny_db_path):
    with pytest.raises(ValueError, match="unknown product"):
        load_draws("powerball")
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `pytest tests/test_db.py -v`
Expected: ModuleNotFoundError or ImportError on `stats.db`.

- [ ] **Step 3: Implement `stats/db.py` minimal (metadata only, no draws yet)**

```python
"""F0 — read-only access to ~/.melate/melate.db.

Loads draws of a product into a normalized DrawData. Path overridable via
the MELATE_DB env var (used by tests).
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PRODUCT_IDS: dict[str, int] = {
    "melate": 40,
    "revancha": 41,
    "revanchita": 34,
    "retro": 30,
}


class DataIntegrityError(RuntimeError):
    def __init__(self, draw: int, msg: str) -> None:
        super().__init__(f"draw {draw}: {msg}")
        self.draw = draw


@dataclass
class DrawData:
    product_name: str
    product_id: int
    range: int
    n_balls: int
    has_additional: bool
    draws_wide: pd.DataFrame
    draws_long: pd.DataFrame
    r7_series: pd.Series | None


def _db_path() -> Path:
    override = os.environ.get("MELATE_DB")
    if override:
        return Path(override)
    return Path.home() / ".melate" / "melate.db"


def load_draws(product: str) -> DrawData:
    if product not in PRODUCT_IDS:
        raise ValueError(f"unknown product: {product!r}")
    product_id = PRODUCT_IDS[product]

    conn = sqlite3.connect(_db_path())
    try:
        meta = conn.execute(
            "SELECT name, range, balls, additional FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if meta is None:
            raise ValueError(f"product id {product_id} not in DB")
        name, range_, n_balls, additional = meta
    finally:
        conn.close()

    # Empty dataframes for now — populated in Task 2.
    empty_wide = pd.DataFrame(columns=["draw", "date", "r1", "r2", "r3", "r4",
                                       "r5", "r6", "r7", "award"])
    empty_long = pd.DataFrame(columns=["draw", "date", "position", "ball"])

    return DrawData(
        product_name=name,
        product_id=product_id,
        range=range_,
        n_balls=n_balls,
        has_additional=bool(additional),
        draws_wide=empty_wide,
        draws_long=empty_long,
        r7_series=None,
    )
```

- [ ] **Step 4: Run test, verify PASS**

Run: `pytest tests/test_db.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/db.py tests/test_db.py
git commit -m "stats(db): load_draws returns DrawData with product metadata"
```

---

## Task 2: F0 — load draws + r7 normalization (Int64 nullable)

**Files:**
- Modify: `stats/db.py`
- Modify: `tests/test_db.py`

**Per design §4 normalization block.**

- [ ] **Step 1: Append failing tests to `tests/test_db.py`**

```python
def test_load_draws_melate_populates_wide_and_long(tiny_db_path):
    data = load_draws("melate")
    # tiny_db_path seeds 50 draws per product
    assert len(data.draws_wide) == 50
    assert len(data.draws_long) == 50 * data.n_balls
    # draws_long has the right columns
    assert list(data.draws_long.columns) == ["draw", "date", "position", "ball"]
    # ball values in valid range
    assert data.draws_long["ball"].between(1, data.range).all()


def test_r7_normalized_to_int64_nullable_for_revancha(tiny_db_path):
    data = load_draws("revancha")
    # has_additional=False ⇒ r7_series is None
    assert data.r7_series is None
    # but draws_wide still has r7 column, and it must be Int64 with all <NA>
    assert data.draws_wide["r7"].dtype.name == "Int64"
    assert data.draws_wide["r7"].isna().all()


def test_r7_populated_int64_for_melate(tiny_db_path):
    data = load_draws("melate")
    assert data.r7_series is not None
    assert data.r7_series.dtype.name == "Int64"
    assert data.r7_series.notna().all()
    assert data.r7_series.between(1, data.range).all()


def test_draws_sorted_ascending_by_draw(tiny_db_path):
    data = load_draws("melate")
    draws = data.draws_wide["draw"].tolist()
    assert draws == sorted(draws)
```

- [ ] **Step 2: Run, verify the 4 new tests FAIL**

Run: `pytest tests/test_db.py -v`
Expected: 4 new failures (assertion errors on shape/dtype).

- [ ] **Step 3: Replace `load_draws` body to load and normalize draws**

In `stats/db.py`, replace everything after the metadata fetch (the `# Empty dataframes for now` block) with:

```python
    # Load results
    query = (
        "SELECT draw, date_time, r1, r2, r3, r4, r5, r6, r7, award "
        "FROM results WHERE product_id = ? ORDER BY draw ASC"
    )
    conn = sqlite3.connect(_db_path())
    try:
        raw = pd.read_sql_query(query, conn, params=(product_id,))
    finally:
        conn.close()

    # Normalize r7: SQLite stores '' for Revancha/Revanchita (melate.pl:366);
    # coerce to nullable Int64 so NA stays NA.
    raw["r7"] = pd.to_numeric(raw["r7"], errors="coerce").astype("Int64")

    # date parsed to datetime, then renamed.
    raw["date_time"] = pd.to_datetime(raw["date_time"], format="%Y-%m-%d")
    raw = raw.rename(columns={"date_time": "date"})

    draws_wide = raw[["draw", "date", "r1", "r2", "r3", "r4", "r5", "r6",
                      "r7", "award"]].reset_index(drop=True)

    # Validate r1..r6.
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    for _, row in draws_wide.iterrows():
        balls = [row[c] for c in ball_cols]
        if len(set(balls)) != n_balls:
            raise DataIntegrityError(row["draw"], "duplicate balls in r1..r6")
        if not all(1 <= b <= range_ for b in balls):
            raise DataIntegrityError(row["draw"], f"ball out of [1, {range_}]")

    # Build long format from r1..r6 only.
    long = draws_wide[["draw", "date"] + ball_cols].melt(
        id_vars=["draw", "date"], value_vars=ball_cols,
        var_name="position", value_name="ball",
    ).sort_values(["draw", "position"]).reset_index(drop=True)

    # r7_series only if has_additional.
    if bool(additional):
        r7_series = draws_wide.set_index("draw")["r7"]
    else:
        r7_series = None

    return DrawData(
        product_name=name,
        product_id=product_id,
        range=range_,
        n_balls=n_balls,
        has_additional=bool(additional),
        draws_wide=draws_wide,
        draws_long=long,
        r7_series=r7_series,
    )
```

- [ ] **Step 4: Run, verify ALL tests PASS**

Run: `pytest tests/test_db.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/db.py tests/test_db.py
git commit -m "stats(db): load and normalize r1-r6 + r7 (Int64 nullable)"
```

---

## Task 3: F0 — DataIntegrityError + integration check against real DB

**Files:**
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add corruption test (synthetic)**

Append to `tests/test_db.py`:

```python
def test_load_draws_raises_on_duplicate_balls(tmp_path, monkeypatch):
    """Inject a corrupt draw into a fresh tiny DB and check we catch it."""
    import sqlite3
    db = tmp_path / "corrupt.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE products (id integer, name text, range integer,
            balls integer, additional integer, url text, filename text);
        CREATE TABLE results (id INTEGER PRIMARY KEY, product_id INTEGER,
            draw integer, date_time TEXT, r1 integer, r2 integer, r3 integer,
            r4 integer, r5 integer, r6 integer, r7 integer, award integer);
        """
    )
    conn.execute(
        "INSERT INTO products VALUES (40,'Melate',56,6,1,'','Melate')"
    )
    # r1 == r2 → duplicate
    conn.execute(
        "INSERT INTO results(product_id,draw,date_time,r1,r2,r3,r4,r5,r6,r7,award)"
        " VALUES (40, 1, '2024-01-01', 5, 5, 6, 7, 8, 9, 10, 30000000)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("MELATE_DB", str(db))
    with pytest.raises(DataIntegrityError) as exc:
        load_draws("melate")
    assert exc.value.draw == 1
```

- [ ] **Step 2: Add integration test against real DB**

Append:

```python
@pytest.mark.integration
def test_load_draws_real_db_matches_count(real_db_path, monkeypatch):
    """N from load_draws must match SELECT COUNT(*) for every product."""
    import sqlite3
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    conn = sqlite3.connect(real_db_path)
    try:
        for name, pid in [("melate", 40), ("revancha", 41),
                          ("revanchita", 34), ("retro", 30)]:
            expected = conn.execute(
                "SELECT COUNT(*) FROM results WHERE product_id = ?", (pid,)
            ).fetchone()[0]
            data = load_draws(name)
            assert len(data.draws_wide) == expected, (
                f"{name}: load_draws gave {len(data.draws_wide)}, DB has {expected}"
            )
    finally:
        conn.close()
```

- [ ] **Step 3: Run unit tests**

Run: `pytest tests/test_db.py -m "not integration" -v`
Expected: all PASS (the corruption test passes immediately because Task 2 already implemented the validator).

- [ ] **Step 4: Run integration test**

Run: `pytest tests/test_db.py -m integration -v`
Expected: PASS (or `skipped` if `~/.melate/melate.db` is absent).

- [ ] **Step 5: Commit**

```bash
git add tests/test_db.py
git commit -m "stats(db): DataIntegrityError + integration test vs real DB (CP1)"
```

> **CHECKPOINT 1** — stop and show the user the integration test output. F0 is verde.

---

## Task 4: Tarea 1 — `chi_square_uniformity`

**Files:**
- Create: `stats/fairness.py`
- Create: `tests/test_fairness.py`

**Per design §5 / fairness.py — Tarea 1.**

- [ ] **Step 1: Write failing tests**

`tests/test_fairness.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.fairness import chi_square_uniformity, ChiSquareResult


def test_chi_square_uniformity_returns_named_result():
    rng = np.random.default_rng(0)
    samples = pd.Series(rng.integers(1, 57, size=10_000))
    result = chi_square_uniformity(samples, n_categories=56)
    assert isinstance(result, ChiSquareResult)
    assert result.dof == 55
    assert 0.0 <= result.p_value <= 1.0
    assert result.observed.shape == (56,)
    assert pytest.approx(result.expected, rel=1e-9) == 10_000 / 56


def test_chi_square_uniform_input_does_not_reject():
    """A genuinely uniform sample should not reject the null."""
    rng = np.random.default_rng(42)
    samples = pd.Series(rng.integers(1, 57, size=100_000))
    result = chi_square_uniformity(samples, n_categories=56)
    assert result.p_value > 0.05


def test_chi_square_skewed_input_rejects():
    """A clearly skewed sample (one category over-represented) rejects."""
    rng = np.random.default_rng(1)
    samples = pd.Series(
        np.concatenate([rng.integers(1, 57, size=10_000),
                        np.full(2_000, 7)])
    )
    result = chi_square_uniformity(samples, n_categories=56)
    assert result.p_value < 1e-6
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_fairness.py -v`
Expected: ImportError on `stats.fairness`.

- [ ] **Step 3: Implement `stats/fairness.py` with chi_square_uniformity**

```python
"""Tier 1 fairness analyses: chi-square, multiple-comparisons correction, Monte Carlo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


@dataclass
class ChiSquareResult:
    stat: float
    dof: int
    p_value: float
    observed: pd.Series  # indexed 1..n_categories
    expected: float
    fig: Figure


def chi_square_uniformity(samples: pd.Series, n_categories: int) -> ChiSquareResult:
    """Goodness-of-fit χ² for samples against discrete uniform over [1, n_categories]."""
    counts = samples.value_counts().reindex(range(1, n_categories + 1), fill_value=0)
    n = int(counts.sum())
    expected = n / n_categories
    stat, p = stats.chisquare(f_obs=counts.values, f_exp=[expected] * n_categories)
    dof = n_categories - 1

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(counts.index, counts.values, color="steelblue", alpha=0.7)
    ax.axhline(expected, color="red", linestyle="--", label=f"expected={expected:.1f}")
    ax.set_xlabel("ball")
    ax.set_ylabel("observed count")
    ax.set_title(f"χ²={stat:.2f}, dof={dof}, p={p:.4f}")
    ax.legend()
    fig.tight_layout()

    return ChiSquareResult(
        stat=float(stat), dof=dof, p_value=float(p),
        observed=counts, expected=expected, fig=fig,
    )
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_fairness.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/fairness.py tests/test_fairness.py
git commit -m "stats(fairness): chi-square goodness-of-fit (tarea 1)"
```

---

## Task 5: Tarea 2 — `correct_pvalues` (Bonferroni + FDR)

**Files:**
- Modify: `stats/fairness.py`
- Modify: `tests/test_fairness.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fairness.py`:

```python
from stats.fairness import correct_pvalues


def test_correct_pvalues_bonferroni_kills_uniform_noise():
    rng = np.random.default_rng(0)
    pvals = pd.Series(rng.uniform(0, 1, size=56))
    result = correct_pvalues(pvals, method="bonferroni")
    assert list(result.columns) == ["pval_raw", "pval_corrected", "significant_at_05"]
    assert result["significant_at_05"].sum() == 0
    # without correction, ~5% would be "significant"
    assert (pvals < 0.05).sum() >= 1


def test_correct_pvalues_bonferroni_keeps_strong_signal():
    pvals = pd.Series([1e-9] + [0.5] * 55)
    result = correct_pvalues(pvals, method="bonferroni")
    assert result["significant_at_05"].iloc[0]
    assert not result["significant_at_05"].iloc[1:].any()


def test_correct_pvalues_fdr_bh_more_permissive_than_bonferroni():
    pvals = pd.Series([0.001, 0.002, 0.003] + [0.5] * 53)
    bonf = correct_pvalues(pvals, method="bonferroni")["significant_at_05"].sum()
    fdr = correct_pvalues(pvals, method="fdr_bh")["significant_at_05"].sum()
    assert fdr >= bonf
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_fairness.py -v`
Expected: 3 new failures (ImportError on `correct_pvalues`).

- [ ] **Step 3: Add `correct_pvalues` to `stats/fairness.py`**

Append:

```python
def correct_pvalues(
    pvals: pd.Series,
    *,
    method: Literal["bonferroni", "fdr_bh"],
) -> pd.DataFrame:
    """Apply multiple-comparisons correction and return raw vs corrected p-values."""
    from statsmodels.stats.multitest import multipletests

    reject, corrected, _, _ = multipletests(pvals.values, alpha=0.05, method=method)
    return pd.DataFrame({
        "pval_raw": pvals.values,
        "pval_corrected": corrected,
        "significant_at_05": reject,
    }, index=pvals.index)
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_fairness.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/fairness.py tests/test_fairness.py
git commit -m "stats(fairness): Bonferroni + FDR_BH correction (tarea 2)"
```

---

## Task 6: Tarea 3 — `simulate_null` (Monte Carlo) + integration sanity on Melate

**Files:**
- Modify: `stats/fairness.py`
- Modify: `tests/test_fairness.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fairness.py`:

```python
from stats.fairness import simulate_null


def _chi2_stat(draws_long_ball: np.ndarray, range_: int) -> float:
    counts = np.bincount(draws_long_ball, minlength=range_ + 1)[1:]
    expected = counts.sum() / range_
    return float(((counts - expected) ** 2 / expected).sum())


def test_simulate_null_chi2_converges_to_chi2_distribution():
    """Empirical χ² distribution under simulated fair draws should match χ²(gl=55)."""
    range_ = 56
    n_balls = 6
    n_draws = 500
    n_sim = 5_000

    dist = simulate_null(
        range_=range_, n_balls=n_balls, n_draws=n_draws, n_sim=n_sim,
        statistic_fn=lambda draws_long_ball: _chi2_stat(draws_long_ball, range_),
        seed=7,
    )
    # KS vs theoretical χ²(55)
    from scipy.stats import chi2 as chi2_dist
    ks_stat, ks_p = stats.kstest(dist, lambda x: chi2_dist.cdf(x, df=range_ - 1))
    assert ks_p > 0.01, f"empirical null diverges from χ²(55): KS p={ks_p}"


def test_simulate_null_seed_reproducible():
    dist_a = simulate_null(range_=56, n_balls=6, n_draws=100, n_sim=200,
                           statistic_fn=lambda x: float(x.sum()), seed=42)
    dist_b = simulate_null(range_=56, n_balls=6, n_draws=100, n_sim=200,
                           statistic_fn=lambda x: float(x.sum()), seed=42)
    np.testing.assert_array_equal(dist_a, dist_b)
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_fairness.py -v`
Expected: 2 new failures.

- [ ] **Step 3: Add `simulate_null` to `stats/fairness.py`**

Append:

```python
def simulate_null(
    *,
    range_: int,
    n_balls: int,
    n_draws: int,
    n_sim: int,
    statistic_fn: Callable[[np.ndarray], float],
    seed: int,
) -> np.ndarray:
    """Simulate `n_sim` fair lotteries, apply `statistic_fn`, return empirical null.

    `statistic_fn` receives a flat 1-D array of length n_draws*n_balls
    (the "long" form, one ball per element).
    """
    rng = np.random.default_rng(seed)
    out = np.empty(n_sim, dtype=float)
    for i in range(n_sim):
        # draw n_balls without replacement per draw, n_draws times
        draws = np.empty((n_draws, n_balls), dtype=np.int32)
        for k in range(n_draws):
            draws[k] = rng.choice(range_, size=n_balls, replace=False) + 1
        out[i] = statistic_fn(draws.reshape(-1))
    return out
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_fairness.py -v`
Expected: 8 passed (may take ~30s due to n_sim=5000).

- [ ] **Step 5: Write integration test for χ² on real Melate**

Append:

```python
from stats.db import load_draws


@pytest.mark.integration
def test_chi_square_melate_real_does_not_reject(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    result = chi_square_uniformity(data.draws_long["ball"], data.range)
    # Reportar p_value siempre. Sanity: p > 0.05 esperado.
    print(f"\nMelate χ²={result.stat:.2f}, dof={result.dof}, p={result.p_value:.4f}")
    assert result.p_value > 0.001, (
        f"χ² strongly rejects uniformity (p={result.p_value:.4e}); "
        "treat as suspected bug per design §3 anti-bug rule"
    )
```

- [ ] **Step 6: Run integration test**

Run: `pytest tests/test_fairness.py -m integration -v -s`
Expected: PASS with χ² + p printed; or `skipped` if real DB absent.

- [ ] **Step 7: Commit**

```bash
git add stats/fairness.py tests/test_fairness.py
git commit -m "stats(fairness): Monte Carlo null + Melate integration check (CP2)"
```

> **CHECKPOINT 2** — stop and show the user the Melate χ² output and the corrected p-values. Tier 1 is verde.

---

## Task 7: Port the `-weight` algorithm from Perl

**Files:**
- Create: `stats/backtest.py`
- Create: `tests/test_backtest.py`

**Per design §5 / backtest.py — Tarea 4.**

The Perl algorithm (`melate.pl:786-800`) sums, per ball, `count_in_segment * level_descending` across N break segments of size B (most-recent segment has highest level). The top `n_balls` weights are the "probable numbers".

- [ ] **Step 1: Write failing test for the weight algorithm**

`tests/test_backtest.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.backtest import predict_weight_balls


def _draws_wide(rows: list[list[int]]) -> pd.DataFrame:
    """Build a draws_wide-like DF from a list of [r1..r6] lists (newest first)."""
    return pd.DataFrame(
        rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]
    ).assign(
        draw=lambda d: range(len(d), 0, -1),  # newest first → draw N..1
        date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def test_predict_weight_one_segment_picks_most_frequent():
    """With a single break segment, the n most frequent balls win."""
    # 4 draws, ball 7 appears in all of them
    rows = [[7, 1, 2, 3, 4, 5],
            [7, 8, 9, 10, 11, 12],
            [7, 13, 14, 15, 16, 17],
            [7, 18, 19, 20, 21, 22]]
    wide = _draws_wide(rows)
    picks = predict_weight_balls(wide, n_balls=1, range_=56,
                                 window=4, breaks=4)
    assert picks == [7]


def test_predict_weight_recent_segment_outweighs_old():
    """Two segments: ball appearing only in the recent segment beats old one."""
    # 6 draws total, broken into 2 segments of 3.
    # ball 50 only in segment 0 (newest 3 draws), level 2
    # ball 10 only in segment 1 (older 3 draws), level 1
    # all other balls fill the rest with no repeats.
    rows_new = [[50, 1, 2, 3, 4, 5],
                [50, 6, 7, 8, 9, 11],
                [50, 12, 13, 14, 15, 16]]
    rows_old = [[10, 17, 18, 19, 20, 21],
                [10, 22, 23, 24, 25, 26],
                [10, 27, 28, 29, 30, 31]]
    wide = _draws_wide(rows_new + rows_old)
    picks = predict_weight_balls(wide, n_balls=1, range_=56,
                                 window=6, breaks=3)
    # weight(50) = 3 * 2 = 6 ; weight(10) = 3 * 1 = 3 → 50 wins
    assert picks == [50]
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_backtest.py -v`
Expected: ImportError on `stats.backtest`.

- [ ] **Step 3: Implement `predict_weight_balls` in `stats/backtest.py`**

```python
"""Tarea 4 — walk-forward backtest of the `-weight` feature from melate.pl."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from scipy import stats


def predict_weight_balls(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
) -> list[int]:
    """Reproduce melate.pl:786-800 weighting on the most-recent `window` draws.

    - Take the last `window` rows of draws_wide (sorted ascending by draw).
    - Split into segments of size `breaks`. Most-recent segment gets highest level.
    - Per ball: sum count_in_segment * level. Return top n_balls.
    """
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    recent = draws_wide.sort_values("draw").tail(window).reset_index(drop=True)
    # Newest first inside `recent` — split so segment 0 is newest.
    recent_rev = recent.iloc[::-1].reset_index(drop=True)
    n_segments = (len(recent_rev) + breaks - 1) // breaks
    weights = np.zeros(range_ + 1, dtype=float)
    for seg_idx in range(n_segments):
        level = n_segments - seg_idx
        seg = recent_rev.iloc[seg_idx * breaks:(seg_idx + 1) * breaks]
        balls = seg[ball_cols].to_numpy().reshape(-1)
        for b in balls:
            weights[int(b)] += level
    # Top n_balls by weight, break ties by lower number (deterministic).
    ranked = sorted(range(1, range_ + 1),
                    key=lambda b: (-weights[b], b))
    return ranked[:n_balls]
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_backtest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/backtest.py tests/test_backtest.py
git commit -m "stats(backtest): port -weight algorithm from melate.pl"
```

---

## Task 8: Backtest — walk-forward harness with anti-leakage assert

**Files:**
- Modify: `stats/backtest.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_backtest.py`:

```python
from stats.backtest import walk_forward_hits, DataLeakageError


def test_walk_forward_hits_counts_correctly():
    """For each draw k, count hits between weight picks (using draws[:k]) and draws[k]."""
    rows = [[1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12],
            [1, 2, 3, 4, 5, 6],  # repeats r1..r6 → weight will favor [1..6]
            [1, 2, 7, 8, 9, 10]]  # k=3: weight on [1..12], actual {1,2,7,8,9,10}
    wide = pd.DataFrame(rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]).assign(
        draw=range(1, 5), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    hits = walk_forward_hits(wide, n_balls=6, range_=56,
                             window=10, breaks=2, start_at=2)
    # We get one hit count per evaluated draw (k=2,3,4) → length 3.
    assert len(hits) == 3
    assert all(0 <= h <= 6 for h in hits)


def test_walk_forward_raises_on_leakage(monkeypatch):
    """Force the predictor to look at draws[k] → must raise DataLeakageError."""
    import stats.backtest as bt
    rows = [[1, 2, 3, 4, 5, 6]] * 5
    wide = pd.DataFrame(rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]).assign(
        draw=range(1, 6), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )

    def leaky_predictor(df, **kw):
        # Cheat: peek at the last row's draw number to "predict" perfectly.
        return list(df.sort_values("draw").iloc[-1][["r1", "r2", "r3", "r4", "r5", "r6"]])

    monkeypatch.setattr(bt, "predict_weight_balls", leaky_predictor)
    with pytest.raises(DataLeakageError):
        walk_forward_hits(wide, n_balls=6, range_=56, window=10,
                          breaks=2, start_at=2)
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_backtest.py -v`
Expected: 2 new failures (ImportError).

- [ ] **Step 3: Add `walk_forward_hits` and `DataLeakageError` to `stats/backtest.py`**

Append:

```python
class DataLeakageError(RuntimeError):
    """Raised when the predictor used a draw at or beyond the evaluation index."""


def walk_forward_hits(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
    start_at: int = 2,
) -> list[int]:
    """For each draw k starting at `start_at`, predict using draws[:k] and count hits vs draws[k]."""
    ordered = draws_wide.sort_values("draw").reset_index(drop=True)
    hits = []
    ball_cols = [f"r{i}" for i in range(1, n_balls + 1)]
    for k in range(start_at, len(ordered) + 1):
        history = ordered.iloc[: k - 1]
        target_row = ordered.iloc[k - 1]
        # Anti-leakage: history must not contain the target draw.
        if (history["draw"] >= target_row["draw"]).any():
            raise DataLeakageError(
                f"predictor history contains draw >= target {target_row['draw']}"
            )
        picks = predict_weight_balls(
            history, n_balls=n_balls, range_=range_,
            window=window, breaks=breaks,
        )
        actual = set(int(target_row[c]) for c in ball_cols)
        hits.append(len(actual & set(picks)))
    return hits
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_backtest.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/backtest.py tests/test_backtest.py
git commit -m "stats(backtest): walk-forward harness + anti-leakage check"
```

---

## Task 9: Backtest — analytical baseline + `weight_walkforward` orchestrator

**Files:**
- Modify: `stats/backtest.py`
- Modify: `tests/test_backtest.py`

**Per design §5 / backtest.py — analytical baseline (hypergeometric), no Monte Carlo.**

- [ ] **Step 1: Write failing tests**

Append to `tests/test_backtest.py`:

```python
from stats.backtest import weight_walkforward, BacktestResult


def test_weight_walkforward_matches_analytical_baseline_on_random_seed_history():
    """A history of uniformly random draws should match E[hits] = n_balls²/range_."""
    rng = np.random.default_rng(123)
    n_draws = 300
    rows = [rng.choice(56, size=6, replace=False) + 1 for _ in range(n_draws)]
    wide = pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, 7)]).assign(
        draw=range(1, n_draws + 1), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    result = weight_walkforward(
        wide, n_balls=6, range_=56, window=60, breaks=10, start_at=61
    )
    assert isinstance(result, BacktestResult)
    expected_rate = 6 * 6 / 56  # ≈ 0.643
    assert pytest.approx(result.hit_rate_baseline_analytical, rel=1e-9) == expected_rate
    # On uniform random data the predictor should not reject the null.
    # Use p > 0.01 (not CI containment) to avoid a ~5% false-fail rate.
    assert result.p_value_vs_baseline > 0.01, (
        f"weight rate {result.hit_rate_weight:.3f} unexpectedly rejects null "
        f"on uniform data (p={result.p_value_vs_baseline}); seed may need tuning"
    )


def test_weight_walkforward_flags_significant_win_as_likely_bug():
    """If weight perfectly predicts (leakage simulation), p must be tiny."""
    # Construct a sequence where draws repeat exactly → weight will always predict perfectly.
    rows = [[1, 2, 3, 4, 5, 6]] * 100
    wide = pd.DataFrame(rows, columns=[f"r{i}" for i in range(1, 7)]).assign(
        draw=range(1, 101), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    result = weight_walkforward(wide, n_balls=6, range_=56, window=20,
                                breaks=5, start_at=21)
    # weight will be ~6/6 every draw → must reject the null overwhelmingly
    assert result.hit_rate_weight > 0.99
    assert result.p_value_vs_baseline < 1e-6
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_backtest.py -v`
Expected: 2 new failures.

- [ ] **Step 3: Add `weight_walkforward` + `BacktestResult`**

Append to `stats/backtest.py`:

```python
@dataclass
class BacktestResult:
    hit_rate_weight: float
    hit_rate_baseline_analytical: float
    baseline_ci_95: tuple[float, float]
    p_value_vs_baseline: float
    hits_per_draw_series: pd.Series
    fig: Figure


def _hypergeom_mean_var(range_: int, n_balls: int) -> tuple[float, float]:
    """E[hits] and Var[hits] for hits = |picks ∩ actual| under uniform picks."""
    # hits ~ Hypergeometric(N=range_, K=n_balls, n=n_balls)
    N, K, n = range_, n_balls, n_balls
    mean = n * K / N
    var = n * K * (N - K) * (N - n) / (N ** 2 * (N - 1))
    return mean, var


def weight_walkforward(
    draws_wide: pd.DataFrame,
    *,
    n_balls: int,
    range_: int,
    window: int,
    breaks: int,
    start_at: int = 2,
) -> BacktestResult:
    hits = walk_forward_hits(
        draws_wide, n_balls=n_balls, range_=range_,
        window=window, breaks=breaks, start_at=start_at,
    )
    hits_arr = np.array(hits, dtype=float)
    n_evals = len(hits_arr)
    hit_rate_weight = float(hits_arr.mean()) / n_balls

    mean_h, var_h = _hypergeom_mean_var(range_, n_balls)
    expected_hits = mean_h
    expected_rate = mean_h / n_balls
    se_mean = (var_h / n_evals) ** 0.5
    ci_lo = (mean_h - 1.96 * se_mean) / n_balls
    ci_hi = (mean_h + 1.96 * se_mean) / n_balls

    # Compare observed mean hits to expected mean via a z-test on the mean.
    z = (hits_arr.mean() - mean_h) / se_mean if se_mean > 0 else 0.0
    p = float(2 * (1 - stats.norm.cdf(abs(z))))

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hits_arr, color="steelblue", alpha=0.5, label="hits / draw")
    ax.axhline(mean_h, color="red", linestyle="--",
               label=f"baseline mean={mean_h:.2f}")
    ax.axhline(mean_h + 1.96 * (var_h ** 0.5), color="red", linestyle=":",
               alpha=0.3, label="±1.96·σ (per-draw)")
    ax.axhline(mean_h - 1.96 * (var_h ** 0.5), color="red", linestyle=":",
               alpha=0.3)
    ax.set_xlabel("evaluation index (k - start_at)")
    ax.set_ylabel("hits per draw")
    ax.set_title(
        f"weight_rate={hit_rate_weight:.3f}, baseline={expected_rate:.3f}, "
        f"p={p:.4f}"
    )
    ax.legend()
    fig.tight_layout()

    return BacktestResult(
        hit_rate_weight=hit_rate_weight,
        hit_rate_baseline_analytical=expected_rate,
        baseline_ci_95=(ci_lo, ci_hi),
        p_value_vs_baseline=p,
        hits_per_draw_series=pd.Series(hits_arr, name="hits"),
        fig=fig,
    )
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_backtest.py -v`
Expected: 6 passed.

- [ ] **Step 5: Integration test on real Melate**

Append:

```python
from stats.db import load_draws


@pytest.mark.integration
def test_weight_walkforward_melate_real_does_not_beat_random(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    # Use a modest window for speed; the full historical can be ~4000 draws.
    result = weight_walkforward(
        data.draws_wide, n_balls=data.n_balls, range_=data.range,
        window=60, breaks=10, start_at=500,  # skip early history
    )
    print(f"\nMelate -weight backtest: rate={result.hit_rate_weight:.3f}, "
          f"baseline={result.hit_rate_baseline_analytical:.3f}, "
          f"p={result.p_value_vs_baseline:.4f}")
    # Expected per design: weight ≈ baseline, p > 0.05
    assert result.p_value_vs_baseline > 0.01, (
        "weight backtest 'beats' random — design §5 anti-bug rule: "
        "probable data leakage, NOT a finding"
    )
```

- [ ] **Step 6: Run integration test**

Run: `pytest tests/test_backtest.py -m integration -v -s`
Expected: PASS (or skipped) with rates printed.

- [ ] **Step 7: Commit**

```bash
git add stats/backtest.py tests/test_backtest.py
git commit -m "stats(backtest): analytical baseline + walk-forward orchestrator (CP3)"
```

> **CHECKPOINT 3** — stop and show the user the backtest output. Tarea 4 is verde, the anti-leakage assert holds.

---

## Task 10: F0.5 — `floor_estimate` with sanity check

**Files:**
- Create: `stats/rollover.py`
- Create: `tests/test_rollover.py`

**Per design §5 / rollover.py.**

- [ ] **Step 1: Write failing test**

`tests/test_rollover.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.rollover import estimate_floor, FloorEstimateWarning


def test_estimate_floor_recovers_known_floor_with_clean_resets():
    floor = 30_000_000
    # 30 draws: accumulate, reset, accumulate, reset...
    awards = []
    current = floor
    for k in range(30):
        if k % 6 == 5:
            current = floor  # reset
        else:
            current += 5_000_000
        awards.append(current)
    s = pd.Series(awards)
    est = estimate_floor(s, eps=0.05)
    assert est == floor


def test_estimate_floor_warns_when_min_and_mode_disagree():
    """If the minimum is anomalous (one outlier), warn and prefer min."""
    awards = pd.Series([1] + [30_000_000] * 5 + [60_000_000] * 5 + [30_000_000] * 5)
    with pytest.warns(FloorEstimateWarning):
        est = estimate_floor(awards, eps=0.05)
    assert est == 1  # conservative: use min
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_rollover.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `estimate_floor` in `stats/rollover.py`**

```python
"""F0.5 — derive jackpot_won / rollover flag from the BOLSA (award) series."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


class FloorEstimateWarning(UserWarning):
    """Raised when the minimum and the Q1-mode of award disagree."""


def estimate_floor(award: pd.Series, *, eps: float = 0.05) -> float:
    """Estimate the jackpot floor from the BOLSA series.

    Use the minimum, but warn if it disagrees with the mode of the lower quartile
    (sign of an outlier or anomalous data point).
    """
    candidate_min = float(award.min())
    q10 = award.quantile(0.10)
    lower = award[award <= q10]
    if lower.empty:
        return candidate_min
    mode_res = stats.mode(lower.values, keepdims=False)
    candidate_mode = float(mode_res.mode)
    if candidate_mode == 0:
        return candidate_min
    rel_diff = abs(candidate_min - candidate_mode) / candidate_mode
    if rel_diff > eps:
        warnings.warn(
            f"floor_estimate: min={candidate_min:.0f} and Q1-mode={candidate_mode:.0f} "
            f"disagree by {rel_diff:.1%}; using min (conservative)",
            FloorEstimateWarning,
        )
    return candidate_min
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_rollover.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/rollover.py tests/test_rollover.py
git commit -m "stats(rollover): estimate_floor with min + mode sanity check"
```

---

## Task 11: F0.5 — `derive_jackpot_won` rule + `ambiguous` flag

**Files:**
- Modify: `stats/rollover.py`
- Modify: `tests/test_rollover.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rollover.py`:

```python
from stats.rollover import derive_jackpot_won


def test_derive_jackpot_won_marks_reset_to_floor():
    floor = 30_000_000
    awards = pd.Series([floor, 50_000_000, 80_000_000, floor, 40_000_000])
    df = derive_jackpot_won(awards)
    # award[k+1] = floor and award[k] >= threshold * floor → True
    # draw indices align with award index
    assert df.loc[2, "jackpot_won"] is True or df.loc[2, "jackpot_won"] == True
    # last draw has no k+1 → NaN
    assert pd.isna(df.loc[4, "jackpot_won"])


def test_derive_jackpot_won_ignores_floor_with_no_buildup():
    """If award did not accumulate enough, do not call it a jackpot win."""
    floor = 30_000_000
    # award[k] is floor itself, then floor again → not a jackpot win
    awards = pd.Series([floor, floor, floor])
    df = derive_jackpot_won(awards)
    assert not df.loc[0, "jackpot_won"]
    assert not df.loc[1, "jackpot_won"]


def test_derive_jackpot_won_returns_expected_columns():
    awards = pd.Series([30_000_000] * 5)
    df = derive_jackpot_won(awards)
    assert set(df.columns) == {"draw", "award", "jackpot_won",
                               "ambiguous", "floor_estimate"}
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_rollover.py -v`
Expected: 3 new failures.

- [ ] **Step 3: Add `derive_jackpot_won` to `stats/rollover.py`**

Append:

```python
def derive_jackpot_won(
    award: pd.Series,
    *,
    eps: float = 0.05,
    threshold: float = 1.2,
) -> pd.DataFrame:
    """Per-draw boolean: was the jackpot won at this draw (BOLSA resets next draw)?

    Rule: jackpot_won[k] := award[k+1] ≤ floor*(1+eps) AND award[k] ≥ floor*threshold.
    Last draw has no k+1 → NaN. Ambiguous = caída sin buildup, marcado para auditoría.
    """
    award = award.reset_index(drop=True)
    floor = estimate_floor(award, eps=eps)
    n = len(award)

    jackpot = pd.Series([pd.NA] * n, dtype="object")
    ambiguous = pd.Series([False] * n, dtype=bool)

    for k in range(n - 1):
        next_low = award.iloc[k + 1] <= floor * (1 + eps)
        curr_high = award.iloc[k] >= floor * threshold
        if next_low and curr_high:
            jackpot.iloc[k] = True
        elif next_low and not curr_high:
            # caída pero sin buildup → ambiguo, no contar como ganador
            jackpot.iloc[k] = False
            ambiguous.iloc[k] = True
        else:
            jackpot.iloc[k] = False

    return pd.DataFrame({
        "draw": range(1, n + 1),
        "award": award.values,
        "jackpot_won": jackpot.values,
        "ambiguous": ambiguous.values,
        "floor_estimate": [floor] * n,
    })
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_rollover.py -v`
Expected: 5 passed.

- [ ] **Step 5: Integration test on real Melate**

Append:

```python
from stats.db import load_draws


@pytest.mark.integration
def test_derive_jackpot_won_real_melate(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    df = derive_jackpot_won(data.draws_wide["award"])
    floor = df["floor_estimate"].iloc[0]
    assert 27_000_000 <= floor <= 35_000_000, (
        f"floor_estimate={floor} outside expected 27-35M for Melate"
    )
    ambiguous_rate = df["ambiguous"].mean()
    print(f"\nMelate floor={floor:.0f}, "
          f"jackpot_won rate={df['jackpot_won'].dropna().mean():.3f}, "
          f"ambiguous rate={ambiguous_rate:.3f}")
    assert ambiguous_rate < 0.05, (
        f"ambiguous rate {ambiguous_rate:.1%} > 5% sanity bound"
    )
```

- [ ] **Step 6: Run integration**

Run: `pytest tests/test_rollover.py -m integration -v -s`
Expected: PASS (or skipped).

- [ ] **Step 7: Commit**

```bash
git add stats/rollover.py tests/test_rollover.py
git commit -m "stats(rollover): derive_jackpot_won + ambiguous flag (F0.5 done)"
```

---

## Task 12: Tarea 5 — `behavior.rollover_excess` over N grid

**Files:**
- Create: `stats/behavior.py`
- Create: `tests/test_behavior.py`

**Per design §5 / behavior.py — N as nuisance parameter.**

- [ ] **Step 1: Write failing tests**

`tests/test_behavior.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from math import comb

from stats.behavior import rollover_excess, RolloverExcessResult


def _jackpot_df_with_rate(rate: float, n: int = 1000) -> pd.DataFrame:
    """rate is the jackpot WIN rate. observed_rollover_rate will equal (1 - rate)."""
    rng = np.random.default_rng(0)
    wins = rng.random(n) < rate
    return pd.DataFrame({
        "draw": range(1, n + 1),
        "award": [30_000_000] * n,
        "jackpot_won": wins,                  # True iff jackpot won that draw
        "ambiguous": [False] * n,
        "floor_estimate": [30_000_000.0] * n,
    })


def test_rollover_excess_uniform_grid_ratio_near_one():
    """If observed rollover rate matches a specific N in the grid, ratio≈1 at that N."""
    range_, n_balls = 56, 6
    p = 1 / comb(range_, n_balls)
    N_target = 30_000_000  # picked so that exp(-N*p) ≈ specific value
    expected_rollover_rate = float(np.exp(-N_target * p))
    df = _jackpot_df_with_rate(rate=1 - expected_rollover_rate, n=2000)

    result = rollover_excess(
        df, range_=range_, n_balls=n_balls,
        n_players_grid=[N_target],
    )
    assert isinstance(result, RolloverExcessResult)
    assert len(result.per_N) == 1
    ratio = result.per_N.loc[0, "ratio"]
    assert 0.9 <= ratio <= 1.1


def test_rollover_excess_observed_above_expected_gives_ratio_gt_1():
    """If observed rollover rate exceeds the Poisson prediction, ratio > 1 at that N."""
    range_, n_balls = 56, 6
    p = 1 / comb(range_, n_balls)
    N = 30_000_000
    poisson_rollover_rate = float(np.exp(-N * p))
    # Simulate observed rollover rate higher than Poisson
    observed_rollover_rate = poisson_rollover_rate + 0.05
    rate_of_win = 1 - observed_rollover_rate
    df = _jackpot_df_with_rate(rate=rate_of_win, n=3000)

    result = rollover_excess(
        df, range_=range_, n_balls=n_balls,
        n_players_grid=[N],
    )
    assert result.per_N.loc[0, "ratio"] > 1.0


def test_rollover_excess_grid_produces_one_row_per_N():
    df = _jackpot_df_with_rate(rate=0.1, n=500)
    grid = [1_000_000, 5_000_000, 10_000_000]
    result = rollover_excess(df, range_=56, n_balls=6, n_players_grid=grid)
    assert list(result.per_N["N"]) == grid
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_behavior.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `stats/behavior.py`**

```python
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


def rollover_excess(
    jackpot_df: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    n_players_grid,
) -> RolloverExcessResult:
    """Compare observed rollover rate against Poisson-uniform predictions for a grid of N."""
    won = jackpot_df["jackpot_won"].dropna()
    # rollover ⇔ NOT won
    rollovers = (won == False).sum()
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
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_behavior.py -v`
Expected: 3 passed.

- [ ] **Step 5: Integration on real Melate**

Append:

```python
from stats.db import load_draws
from stats.rollover import derive_jackpot_won


@pytest.mark.integration
def test_rollover_excess_melate_real_lower_bound(real_db_path, monkeypatch):
    monkeypatch.setenv("MELATE_DB", str(real_db_path))
    data = load_draws("melate")
    jackpot_df = derive_jackpot_won(data.draws_wide["award"])
    grid = [1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000]
    result = rollover_excess(jackpot_df, range_=data.range,
                             n_balls=data.n_balls, n_players_grid=grid)
    print(f"\nMelate observed rollover rate = {result.observed_rollover_rate:.3f}")
    print(result.per_N.to_string(index=False))
    # Lower bound: at the largest N (most favorable to null), ratio should still be ≥ 1
    largest_N_row = result.per_N.iloc[-1]
    assert largest_N_row["ratio"] >= 1.0, (
        "rollover excess vanishes at the largest N — either no conscious selection "
        "OR F0.5 is mis-detecting jackpot wins. Check first."
    )
```

- [ ] **Step 6: Run integration**

Run: `pytest tests/test_behavior.py -m integration -v -s`
Expected: PASS (or skipped) with the per-N table printed.

- [ ] **Step 7: Commit**

```bash
git add stats/behavior.py tests/test_behavior.py
git commit -m "stats(behavior): rollover_excess over N grid (tarea 5, CP4)"
```

> **CHECKPOINT 4** — stop and show the user the full per-N table for Melate. The three baldes (justice/backtest/behavior) are now individually green.

---

## Task 13: `report.build_report` — Markdown + figures embedding

**Files:**
- Create: `stats/report.py`
- Modify: `tests/test_fairness.py` (small fixture-based check is fine in test_report.py)
- Create: `tests/test_report.py`

- [ ] **Step 1: Write failing tests**

`tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_report.py -v`
Expected: ImportError on `stats.report`.

- [ ] **Step 3: Implement `stats/report.py`**

```python
"""Assemble Markdown + figures report from analysis results."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/report.py tests/test_report.py
git commit -m "stats(report): Markdown + figures with ATENCIÓN banner on mismatch"
```

---

## Task 14: `cli.py` — entry point, dispatch, default output dir

**Files:**
- Create: `stats/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write smoke test**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/test_cli.py -v`
Expected: nonzero exit from subprocess (no entry point yet).

- [ ] **Step 3: Implement `stats/cli.py` + `stats/__main__.py`**

`stats/cli.py`:

```python
"""CLI entry point: python -m stats --product X --analyses Y,Z --output DIR."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from stats.db import load_draws
from stats.fairness import chi_square_uniformity
from stats.backtest import weight_walkforward
from stats.rollover import derive_jackpot_won
from stats.behavior import rollover_excess
from stats.report import build_report


ANALYSES = {"chi2", "backtest", "rollover", "behavior", "all"}


def _run_chi2(data) -> dict:
    res = chi_square_uniformity(data.draws_long["ball"], data.range)
    return {
        "title": "Chi-square goodness-of-fit (r1..r6)",
        "summary": f"stat={res.stat:.2f}, dof={res.dof}, p={res.p_value:.4f}",
        "figure": res.fig,
        "expected_per_spec": "p > 0.05 (no rechazar uniformidad)",
        "matches_expectation": res.p_value > 0.05,
    }


def _run_backtest(data) -> dict:
    res = weight_walkforward(
        data.draws_wide, n_balls=data.n_balls, range_=data.range,
        window=60, breaks=10, start_at=min(500, max(2, len(data.draws_wide) // 4)),
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
        requested = {"chi2", "backtest", "behavior"}

    sections = []
    if "chi2" in requested:
        sections.append(_run_chi2(data))
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
```

`stats/__main__.py`:

```python
from stats.cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add stats/cli.py stats/__main__.py tests/test_cli.py
git commit -m "stats(cli): entry point with chi2/backtest/behavior/all dispatch"
```

---

## Task 15: End-to-end integration smoke test on real Melate

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write failing test**

`tests/test_e2e.py`:

```python
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
    # ATENCIÓN banner should NOT appear if everything is in the expected zone
    print(f"\n--- report.md ---\n{body[:2000]}\n--- end ---")
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_e2e.py -m integration -v -s`
Expected: PASS (or skipped). The report content prints to stdout for review.

- [ ] **Step 3: Manual review of the report**

Open `tmp_path/report.md` (path printed by `print(f"report written to ...")`). Confirm:
- Three sections present (χ², backtest, rollover excess).
- Each section has its figure embedded.
- No "ATENCIÓN" banner under expected outcome.

- [ ] **Step 4: Run the full test suite one last time**

Run: `pytest -v`
Expected: all unit tests pass; integration tests pass or skip cleanly.

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e.py
git commit -m "stats: end-to-end test on real Melate (v1 done)"
```

> **v1 COMPLETE.** Show the user the final report. Decide whether to proceed to Task 13 of the original spec (scraping, opt-in) or stop here.

---

## Out of scope for v1 (explicit deuda)

Per design §2, the following are NOT implemented in v1 and remain documented in
`melate-stats-spec.md` for future iterations:

- Tarea 6 (Bayesian Dirichlet-multinomial)
- Tarea 7 (multivariate co-occurrence vs hypergeometric)
- Tarea 8 (gaps K-S vs geometric)
- Tarea 9 (runs / autocorrelation)
- Tarea 10 (drift / CUSUM / Pettitt)
- Tarea 11 (NIST / dieharder / TestU01)
- Tarea 12 (wheeling)
- Tarea 13 (scraping winners by category) — `stats/ingest.py` is reserved but not built.
