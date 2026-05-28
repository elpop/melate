# Diseño — Módulo de inferencia estadística sobre Melate

**Fecha:** 2026-05-28
**Autor:** Sabas (con Claude Code, vía superpowers:brainstorming)
**Spec base:** [`melate-stats-spec.md`](../../../melate-stats-spec.md)
**Repo base:** [`elpop/melate`](https://github.com/elpop/melate) (fork local: `electroniccats/melate`)
**Estado:** aprobado para pasar a `writing-plans`.

**Canonicidad:** este design doc es **canónico para la v1**. El spec original
`melate-stats-spec.md` queda como *vision document* del módulo completo (Tiers 1–4) y
referencia a este diseño para lo que efectivamente se implementa. Si los dos divergen,
manda éste.

---

## 1. Objetivo y restricciones

Construir un módulo Python (`stats/`) que haga **inferencia estadística** sobre el histórico
de sorteos almacenado en `~/.melate/melate.db` (SQLite, poblada por `melate.pl`). El módulo
verifica si la lotería es justa, demuestra empíricamente que la predicción no funciona, y
cuantifica el único margen real de valor esperado (selección consciente de los jugadores).

**Restricciones rectoras:**
- Solo lectura sobre la DB existente. No tocar el código Perl. (Excepción acotada: `ingest.py`
  opcional puede escribir en una tabla nueva `winners`, separada.)
- No producir ninguna recomendación de "números futuros". El producto es inferencia, no
  predicción.
- Cada análisis debe ser una función pura testeable de forma aislada.

---

## 2. Decisiones cerradas en brainstorming

1. **Bolas analizadas:** el sorteo principal es r1–r6. La bola adicional r7 (productos
   Melate id=40 y Retro id=30) se analiza por separado, en su propio canal. Nunca se mezcla
   con r1–r6 en la misma prueba.
2. **Alcance v1:** `F0 → tareas 1+2+3 → tarea 4 → F0.5 → tarea 5`. Esto cubre la narrativa
   completa (justicia + backtest del `-weight` + rollover/selección consciente). Tareas 6–10
   del spec quedan fuera de v1 como extensiones futuras.
3. **Tarea 13 (scraping de ganadores por categoría):** opcional, deshabilitada por defecto.
   No bloquea v1. Si la v1 sale bien, se ejecuta como complemento; si no, queda como deuda
   explicitada.
4. **Enfoque arquitectónico:** modular estricto (un módulo por preocupación, función pura
   por análisis, TDD por módulo).

---

## 3. Arquitectura

```
melate/                              # repo actual, raíz del proyecto
├── melate.pl, chispazo.pl, ...      # código Perl intacto
├── pyproject.toml                   # config Python (Stats v1)
├── stats/                           # módulo nuevo, Python 3.11+
│   ├── __init__.py
│   ├── db.py                        # F0: acceso SQLite → DataFrame
│   ├── rollover.py                  # F0.5: deriva jackpot_won desde BOLSA
│   ├── fairness.py                  # tareas 1, 2, 3
│   ├── backtest.py                  # tarea 4 (walk-forward del -weight)
│   ├── behavior.py                  # tarea 5 (selección consciente)
│   ├── report.py                    # ensambla Markdown + figuras
│   ├── cli.py                       # `python -m stats ...`
│   └── ingest.py                    # tarea 13 (OPCIONAL, off por defecto)
├── tests/                           # pytest, una suite por módulo
│   ├── conftest.py                  # fixtures: mini-DB sintética + DB real opcional
│   ├── test_db.py
│   ├── test_rollover.py
│   ├── test_fairness.py
│   ├── test_backtest.py
│   ├── test_behavior.py
│   └── test_cli.py                  # smoke test del entry point
└── report/                          # output (en .gitignore)
    └── melate-stats-YYYYMMDD/
        ├── report.md
        └── figs/*.png
```

**Stack:** Python 3.11+, `pandas`, `numpy`, `scipy.stats`, `statsmodels`, `matplotlib`.
SQLite via `sqlite3` de stdlib. Sin `sqlalchemy`. Sin Jupyter como dependencia obligatoria.
Dependencias y entry point en `pyproject.toml` (no `requirements.txt`).

**Principios:**
- Solo lectura sobre `~/.melate/melate.db` (path overridable por env `MELATE_DB`).
- Una función pura por análisis: `f(draws_df, **opts) -> (result_dict, figure)`.
- Sin estado global. Sin singletons.
- r1–r6 y r7 viajan por canales separados; nunca se mezclan dentro de una prueba.

---

## 4. Representación de datos

Función central de `db.py`:

```python
load_draws(product: str) -> DrawData
```

donde:

```python
@dataclass
class DrawData:
    product_name: str            # "Melate"
    product_id: int              # 40
    range: int                   # 56 (leído de products)
    n_balls: int                 # 6
    has_additional: bool         # True (additional == 1)
    draws_wide: pd.DataFrame     # cols: draw, date, r1..r6, [r7], award
    draws_long: pd.DataFrame     # cols: draw, date, position, ball  (SIEMPRE solo r1..r6)
    r7_series: pd.Series | None  # indexed by draw, valor o NaN
                                 # None si has_additional == False
                                 # poblada si has_additional == True (Melate, Retro)
```

`draws_long` **nunca** incluye r7 (es el canal del "sorteo principal"). El análisis de r7
opera sobre `r7_series` explícitamente, en una llamada separada.

**Por qué dos formatos:**
- `draws_wide`: eficiente para co-ocurrencia, backtest, serie de `award` para rollover.
- `draws_long`: lo que esperan chi² / gaps / runs (una fila por bola observada).
- `r7_series`: aislado, para que un análisis aplicable también a r7 opere sobre esta serie sin
  contaminar `draws_long`.

**Normalización obligatoria en `load_draws`:**
- Leer `range`, `additional` de la tabla `products` (nunca hardcodear).
- Normalizar la columna r7 de SQLite. El código Perl inserta `''` (string vacío) en r7
  para Revancha/Revanchita (`melate.pl:366`); al leer con pandas la columna queda como
  `object`. Aplicar explícitamente:
  ```python
  df["r7"] = pd.to_numeric(df["r7"], errors="coerce").astype("Int64")
  ```
  `Int64` (con I mayúscula) es el tipo nullable de pandas — preserva NaN sin caer a `float64`.
- `date` parseada a `datetime64`; sorteos ordenados por `draw` ascendente.
- `r7_series` se materializa si y solo si `has_additional == True`; si no, queda en `None`.
- Validar: cada sorteo tiene 6 valores únicos en r1–r6, todos en `[1, range]`. Si no,
  levantar `DataIntegrityError(draw=<n>)`.

**Data flow del pipeline:**

```
~/.melate/melate.db
       │
       ▼
   db.load_draws("melate")   ──► DrawData
       │
       ├──► fairness.chi_square_uniformity(draws.draws_long.ball, draws.range)
       ├──► fairness.chi_square_uniformity(draws.r7_series, draws.range)  [si has_additional]
       │    # banda nula del χ² = sanity band analítica [gl − 2√(2·gl), gl + 2√(2·gl)],
       │    # reportada junto con el p-valor exacto. simulate_null NO se invoca aquí:
       │    # el χ² goodness-of-fit ya tiene null cerrado vía scipy.stats.chisquare,
       │    # y la sanity band cubre la lectura visual. simulate_null queda como
       │    # infraestructura para Tier 3+ (tareas 8 K-S de gaps y 10 drift/CUSUM),
       │    # donde la distribución nula sí carece de forma cerrada manejable.
       ├──► backtest.weight_walkforward(draws.draws_wide,
       │                                 range_=draws.range, n_balls=draws.n_balls)
       │                                 # baseline analítico (hipergeométrica), no Monte Carlo
       ├──► rollover.derive_jackpot_won(draws.draws_wide["award"])        ──► jackpot_df
       └──► behavior.rollover_excess(jackpot_df, range_=draws.range,
                                      n_balls=draws.n_balls, n_players_grid=[...])
       │
       ▼
   report.build_report(all_results)
       ──► report/melate-stats-YYYYMMDD/report.md
```

---

## 5. Contrato por módulo

### `db.py` — F0

```python
load_draws(product: str) -> DrawData
```

**Aceptación:**
- Para los 4 productos: `load_draws(p).draws_long.shape[0] == n_draws * n_balls`.
- `r7_series is None` ⟺ `has_additional == False`.
- Para Melate/Retro: `r7_series.notna().all()` y `r7_series.dtype == "Int64"`
  (no quedan `''` colados ni cae a `float64`).
- Sorteo corrupto sintético → levanta `DataIntegrityError(draw=<n>)`.

---

### `rollover.py` — F0.5

```python
derive_jackpot_won(award: pd.Series, *, eps: float = 0.05, threshold: float = 1.2) -> pd.DataFrame
```

- Estima `floor_estimate` empíricamente con doble verificación:
  - `candidate_min = award.min()`
  - `candidate_mode = scipy.stats.mode(award[award <= award.quantile(0.10)]).mode`
  - Si `|candidate_min − candidate_mode| / candidate_mode > eps` → warning y usar
    `candidate_min` (más conservador).
  - Si concuerdan → `floor_estimate = candidate_min`.
- Regla robusta: `jackpot_won[k] := award[k+1] ≤ floor*(1+eps) AND award[k] ≥ floor*threshold`.
- Maneja último sorteo (`NaN`, no `False`).
- Columnas del DataFrame de salida: `draw`, `award`, `jackpot_won` (bool|NaN),
  `ambiguous` (bool), `floor_estimate` (constante).

**Aceptación:**
- Sobre Melate real, `floor_estimate ≈ 30_000_000` (±10%); `floor_estimate == award.min()`
  modulo el sanity check.
- Reset documentado 4197→4198 marca `jackpot_won[4197] == True`.
- `ambiguous.mean() < 0.05` (sanity: si más, hay bug o sorteos especiales no anticipados).
- Test sintético: serie escalera con resets a piso conocido → recupera flags exactos.

---

### `fairness.py` — Tareas 1, 2, 3

**Tarea 1 — Chi-cuadrado de bondad de ajuste**
```python
chi_square_uniformity(samples: pd.Series, n_categories: int) -> ChiSquareResult
# ChiSquareResult: stat, dof, p_value, observed: pd.Series, expected: float, fig
```
- Funciona idéntico para r1–r6 (concatenación de `draws_long.ball`) y para r7 (`r7_series`).

**Aceptación:** el reporte SIEMPRE muestra `p_value` exacto y `stat`. Sobre Melate real,
p > 0.05 esperado; χ² dentro de `[gl − 2√(2·gl), gl + 2√(2·gl)]` como sanity (≈95% del nulo).
La banda no sustituye al p-valor; ambos van al reporte. Gráfica de frecuencias observadas
vs banda esperada.

**Tarea 2 — Corrección de comparaciones múltiples**
```python
correct_pvalues(pvals: pd.Series, *, method: Literal["bonferroni", "fdr_bh"]) -> pd.DataFrame
# columnas: pval_raw, pval_corrected, significant_at_05
```
- Transversal: cualquier prueba por-bola la aplica antes de reportar.

**Aceptación:** sobre 56 p-valores generados uniformes en [0,1], ninguno sobrevive a
Bonferroni 0.05; ~5% sobreviven sin corregir (sanity).

**Tarea 3 — Monte Carlo**
```python
simulate_null(range_: int, n_balls: int, n_draws: int, n_sim: int,
              statistic_fn: Callable, *, seed: int) -> np.ndarray
```
- Genera `n_sim` loterías sintéticas justas, aplica `statistic_fn`, devuelve distribución empírica.
- **Uso en v1:** infraestructura testeada pero NO surfaceada en el CLI/reporte. El χ² de
  goodness-of-fit del v1 usa la distribución analítica de `scipy.stats.chisquare` más la
  sanity band cerrada del Tarea 1; añadir Monte Carlo encima sería ceremonia equivalente.
  El consumidor real de `simulate_null` son las tareas 8 (K-S de gaps vs. geométrica) y
  10 (drift/CUSUM), donde la distribución nula sí carece de forma cerrada manejable. Se
  mantiene en `fairness.py` con sus tests para que esas tareas la encuentren lista.

**Aceptación:** la distribución empírica de χ² bajo nulo converge (KS contra χ²(gl) teórica
con p > 0.05) con `n_sim ≥ 10_000`.

---

### `backtest.py` — Tarea 4

```python
weight_walkforward(draws_wide: pd.DataFrame, *, window: int, breaks: int,
                   range_: int, n_balls: int) -> BacktestResult
# BacktestResult: hit_rate_weight, hit_rate_baseline_analytical,
#                 baseline_ci_95, p_value_vs_baseline,
#                 hits_per_draw_series, fig
```

- Reproduce **exactamente** el algoritmo de `melate.pl:786-800` (suma ponderada por segmentos,
  nivel decreciente, más reciente pesa más).
- Walk-forward: en cada sorteo `k`, usa solo `draws[:k]` para producir `n_balls` "números
  probables"; compara contra `draws[k]`.
- **Baseline analítico (no Monte Carlo):** bajo selección uniforme, el número de aciertos
  por sorteo es hipergeométrica con parámetros `(N=range_, K=n_balls, n=n_balls)`. La tasa
  esperada de aciertos es `E[hits] = n_balls² / range_` (= 0.643 para Melate). El IC95 sobre
  el agregado de `n_draws_evaluados` sorteos sale de la varianza analítica de la hipergeométrica.
  Se evita Monte Carlo porque la distribución es conocida y cerrada; usar simulación aquí
  sería ceremonia innecesaria.
- Comparación: test binomial / proporciones del `hit_rate_weight` contra el `E[hits]`
  analítico. Reportar `p_value_vs_baseline`.

**Aceptación crítica (anti-bug, no opcional):**
- `assert max(draw_idx_used) < k` en cada iteración (test explícito contra data leakage).
  Esta es la primera verificación que corre; si falla, ningún otro resultado se reporta.
- `hit_rate_weight` ∈ `baseline_ci_95` y `p_value_vs_baseline > 0.05` (no rechazar igualdad
  al azar).
- Si el backtest "gana" significativamente → el test debe fallar con mensaje:
  *"probable data leakage, NO es hallazgo, auditar la ventana walk-forward"*.

---

### `behavior.py` — Tarea 5

```python
rollover_excess(
    jackpot_df: pd.DataFrame,
    *,
    range_: int,
    n_balls: int,
    n_players_grid: list[int] | np.ndarray = (1_000_000, 5_000_000, 10_000_000,
                                              25_000_000, 50_000_000),
) -> RolloverExcessResult
# RolloverExcessResult:
#   observed_rollover_rate: float
#   per_N: pd.DataFrame   # cols: N, expected_rate_poisson, ratio, p_value, ci_95
#   fig                   # curva ratio vs N + banda de IC
```

- `p_jackpot_per_ticket = 1 / C(range_, n_balls)`.
- Para cada `N` en `n_players_grid`: `expected_rollover_rate(N) = exp(-N * p_jackpot_per_ticket)`
  (Poisson bajo elección uniforme).
- `ratio(N) = observed_rate / expected_rollover_rate(N)`.
- Test: razón de tasas / proporción observada vs esperada; p-value por bola de N.
- **N tratado como nuisance parameter**: el reporte presenta el ratio para todo el grid de N,
  no un número único. La conclusión se enuncia como *"incluso bajo el N más favorable al
  null (el más alto del grid), el exceso de rollovers es ≥ X"*. Esto evita comprometerse
  con un N específico que requeriría conocer el reglamento y la fracción de ventas que va
  al pozo.

**Aceptación:**
- El output del reporte incluye literal: *"este número subestima el efecto real;
  una fracción desconocida de jugadores usa Quick Pick (selección automática), que es uniforme
  y atenúa el exceso de rollovers medible."*
- El output del reporte incluye literal: *"N (número de boletos vendidos por sorteo) se trata
  como parámetro de molestia; el resultado se presenta sobre un rango plausible de N en vez
  de fijar un valor único."*
- Sobre Melate real, `ratio > 1` para todo el grid `n_players_grid` razonable (cota inferior
  consistente con la literatura internacional de *conscious selection*).

---

### `report.py`

```python
build_report(results: dict[str, Any], output_dir: Path) -> Path
```

- Genera `report.md` con secciones por tarea, embebe figuras desde `figs/`.
- Cada sección incluye: estadísticos, p-valores (raw y corregidos donde aplique),
  interpretación contrastada contra "Resultados esperados" del spec.
- **Bandera obligatoria:** si algún resultado contradice lo esperado, el reporte abre con un
  bloque "ATENCIÓN: revisar como posible bug antes de reportar como hallazgo" listando cuáles.

---

### `cli.py`

```bash
python -m stats --product melate --analyses all --output report/
python -m stats --product melate --analyses chi2,backtest
python -m stats --product retro --analyses chi2     # r7 incluido automáticamente si has_additional
```

Subcomandos: `chi2`, `backtest`, `rollover`, `behavior`, `all`. Output a
`report/melate-stats-YYYYMMDD/` por default.

---

## 6. Estrategia de tests

**Disciplina:** TDD por módulo según `superpowers:test-driven-development`.
Test rojo → implementación mínima → verde → refactor.

**Fixtures (en `tests/conftest.py`):**
- `tiny_db_path`: SQLite efímero (vía `tmp_path`) con esquema real y ~50 sorteos sintéticos
  por producto. **Alcance acotado: solo lógica** (parsing, normalización de r7=`''`, validación
  de rangos, edge cases del piso de BOLSA, walk-forward sin leakage). NO valida propiedades
  estadísticas — 50 sorteos × 6 bolas tiene gl=55 con ruido enorme.
- `real_db_path`: marca `pytest.mark.integration`, salta si no existe `~/.melate/melate.db`.
  Aquí se validan las propiedades estadísticas que el spec espera (χ² no rechaza, backtest
  ≈ azar, ratio de rollovers > 1).

**Niveles:**
1. **Unit** (rápidos, sin DB real) — funciones puras contra fixtures sintéticas. Verifican
   lógica, no propiedades estadísticas.
2. **Integration** (lentos, requieren DB poblada, `@pytest.mark.integration`) — validan
   que sobre datos reales los resultados caen donde el spec dice.
3. **Anti-bug (críticos)** — asserts contra data leakage en backtest, contra detección espuria
   de rollover, etc. Los que el spec identifica como "señales de bug, no de hallazgo". Estos
   corren en ambos niveles (sintético y real).

---

## 7. Checkpoints de revisión humana

Antes de avanzar de un checkpoint al siguiente: correr tests, mostrar output del reporte
parcial, esperar OK explícito.

| Checkpoint | Cuándo | Qué se entrega |
|---|---|---|
| CP1 | F0 verde | `load_draws` funciona para los 4 productos; conteos coinciden con `SELECT COUNT(*) FROM results` por producto |
| CP2 | Tareas 1+2+3 verdes | Reporte parcial con χ² + corrección + Monte Carlo para Melate; gráficas embebidas |
| CP3 | Tarea 4 verde | Reporte parcial con backtest del `-weight`; assert anti-leakage explícito pasa |
| CP4 | F0.5 + Tarea 5 verdes | Reporte v1 completo con los tres baldes (justicia / backtest / selección consciente) |
| CP5 (opcional) | Tarea 13 | Solo si se activa explícitamente; reporte v2 con conteo real de ganadores |

---

## 8. Relación con el spec original (`melate-stats-spec.md`)

Este design doc es **canónico para la v1**. El spec original queda como *vision document*
del módulo completo (Tiers 1–4, todas las extensiones futuras).

**Única acción a aplicar al spec original:** añadir al inicio una nota:

> *"V1 se implementa según `docs/superpowers/specs/2026-05-28-melate-stats-design.md`,
> que es canónico para lo efectivamente entregado. Este documento (`melate-stats-spec.md`)
> mantiene la visión completa del módulo (incluyendo Tiers 6–13 fuera de v1)."*

NO se intenta sincronizar los dos documentos. Si divergen, manda el design doc para v1.
Los Tiers 6–13 del spec original quedan como deuda explicitada para futuras iteraciones.

---

## 9. Próximo paso

Invocar `superpowers:writing-plans` con este diseño como input para producir el plan de
implementación detallado (con pasos, comandos, criterios verificables por paso).
