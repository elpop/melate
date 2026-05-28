# Diseño — Módulo de inferencia estadística sobre Melate

**Fecha:** 2026-05-28
**Autor:** Sabas (con Claude Code, vía superpowers:brainstorming)
**Spec base:** [`melate-stats-spec.md`](../../../melate-stats-spec.md)
**Repo base:** [`elpop/melate`](https://github.com/elpop/melate) (fork local: `electroniccats/melate`)
**Estado:** aprobado para pasar a `writing-plans`.

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
melate/                           # repo actual (intacto, en Perl)
├── melate.pl, chispazo.pl, ...   # nada se toca
└── stats/                        # módulo nuevo, Python 3.11+
    ├── __init__.py
    ├── db.py                     # F0: acceso SQLite → DataFrame
    ├── rollover.py               # F0.5: deriva jackpot_won desde BOLSA
    ├── fairness.py               # tareas 1, 2, 3
    ├── backtest.py               # tarea 4 (walk-forward del -weight)
    ├── behavior.py               # tarea 5 (selección consciente)
    ├── report.py                 # ensambla Markdown + figuras
    ├── cli.py                    # `python -m stats ...`
    ├── ingest.py                 # tarea 13 (OPCIONAL, off por defecto)
    ├── requirements.txt
    └── tests/
        ├── conftest.py           # fixtures: mini-DB sintética + DB real opcional
        ├── test_db.py
        ├── test_rollover.py
        ├── test_fairness.py
        ├── test_backtest.py
        └── test_behavior.py
report/                            # output (en .gitignore)
└── melate-stats-YYYYMMDD/
    ├── report.md
    └── figs/*.png
```

**Stack:** Python 3.11+, `pandas`, `numpy`, `scipy.stats`, `statsmodels`, `matplotlib`.
SQLite via `sqlite3` de stdlib. Sin `sqlalchemy`. Sin Jupyter como dependencia obligatoria.

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
- Convertir `r7 = ''` (string vacío que mete el código Perl en Revancha/Revanchita,
  `melate.pl:366`) → `NaN`.
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
       ├──► fairness.simulate_null(draws.range, ...)                      ──► null_dist
       ├──► backtest.weight_walkforward(draws.draws_wide, null_dist)
       ├──► rollover.derive_jackpot_won(draws.draws_wide["award"])        ──► jackpot_df
       └──► behavior.rollover_excess(jackpot_df, ...)
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
- Para los 4 productos: `load_draws(p).draws_long.shape[0] == n_draws * 6`.
- `r7_series is None` ⟺ `has_additional == False`.
- Para Melate/Retro: `r7_series.notna().all()` (no quedan `''` colados).
- Sorteo corrupto sintético → levanta `DataIntegrityError(draw=<n>)`.

---

### `rollover.py` — F0.5

```python
derive_jackpot_won(award: pd.Series, *, eps: float = 0.05, threshold: float = 1.2) -> pd.DataFrame
```

- Estima `floor_estimate` empíricamente (moda del cuartil inferior de la serie).
- Regla robusta: `jackpot_won[k] := award[k+1] ≤ floor*(1+eps) AND award[k] ≥ floor*threshold`.
- Maneja último sorteo (`NaN`, no `False`).
- Columnas del DataFrame de salida: `draw`, `award`, `jackpot_won` (bool|NaN),
  `ambiguous` (bool), `floor_estimate` (constante).

**Aceptación:**
- Sobre Melate real, `floor_estimate ≈ 30_000_000` (±10%).
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

**Aceptación:** sobre Melate real, p > 0.05; χ² dentro de `[gl − 2√(2·gl), gl + 2√(2·gl)]`.
Gráfica frecuencias observadas vs banda esperada.

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

**Aceptación:** la distribución empírica de χ² bajo nulo converge (KS contra χ²(gl) teórica
con p > 0.05) con `n_sim ≥ 10_000`.

---

### `backtest.py` — Tarea 4

```python
weight_walkforward(draws_wide: pd.DataFrame, *, window: int, breaks: int,
                   null_sim: np.ndarray) -> BacktestResult
# BacktestResult: hit_rate_weight, hit_rate_random, ci_95, p_value,
#                 hits_per_draw_series, fig
```

- Reproduce **exactamente** el algoritmo de `melate.pl:786-800` (suma ponderada por segmentos,
  nivel decreciente, más reciente pesa más).
- Walk-forward: en cada sorteo `k`, usa solo `draws[:k]` para producir 6 "números probables";
  compara contra `draws[k]`.
- Baseline: misma función con selección uniforme aleatoria, vía `simulate_null`.

**Aceptación crítica (anti-bug, no opcional):**
- `assert max(draw_idx_used) < k` en cada iteración (test explícito contra data leakage).
- Tasa de acierto del `-weight` ∈ `[random_lower_ci, random_upper_ci]` con p > 0.05.
- Si el backtest "gana" → el test debe fallar con mensaje:
  *"probable data leakage, NO es hallazgo, auditar la ventana walk-forward"*.

---

### `behavior.py` — Tarea 5

```python
rollover_excess(jackpot_df: pd.DataFrame, *, expected_p_jackpot: float,
                n_players_per_draw: int | None = None) -> RolloverExcessResult
# RolloverExcessResult: observed_rate, expected_poisson_rate, ratio,
#                      p_value, ci_95, fig
```

- `expected_p_jackpot = 1 / C(range, 6)` por boleto; combinado con `n_players_per_draw`
  estimado o pasado como parámetro, produce la tasa esperada de rollovers bajo elección uniforme.
- Test: tasa observada de rollovers (de F0.5) vs Poisson uniforme.
- Reporta el ratio observado/esperado como **cota inferior** del efecto de selección consciente.

**Aceptación:**
- El output del reporte incluye literal: *"este número subestima el efecto real;
  una fracción desconocida de jugadores usa Quick Pick (selección automática), que es uniforme
  y atenúa el exceso de rollovers medible."*
- Sobre Melate real, ratio > 1 esperado (cota inferior consistente con la literatura
  internacional de *conscious selection*).

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
  por producto. Permite tests rápidos sin depender de `~/.melate/melate.db`.
- `real_db_path`: marca `pytest.mark.integration`, salta si no existe `~/.melate/melate.db`.

**Niveles:**
1. **Unit** (rápidos, sin DB real) — todas las funciones puras contra fixtures sintéticas.
2. **Integration** (lentos, requieren DB poblada, `@pytest.mark.integration`) — validan
   que sobre datos reales los resultados caen donde el spec dice.
3. **Anti-bug (críticos)** — asserts contra data leakage en backtest, contra detección espuria
   de rollover, etc. Los que el spec identifica como "señales de bug, no de hallazgo".

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

## 8. Deltas a aplicar al spec original (`melate-stats-spec.md`)

Para que el spec refleje las decisiones tomadas aquí:

1. Añadir bloque "Decisiones cerradas para v1" en sección 1 (las 4 de §2 de este diseño).
2. Reemplazar el árbol de carpetas propuesto por el de §3 de este diseño (con `tests/` explícito).
3. F0: añadir contrato exacto de `load_draws` y dataclass `DrawData`.
4. F0.5: añadir parámetros `eps=0.05`, `threshold=1.2` y columna `ambiguous`; criterio
   cuantitativo `ambiguous < 5%`.
5. Tarea 4: añadir el assert anti-leakage como criterio de aceptación.
6. Tarea 5: convertir el caveat Quick Pick de párrafo a requisito de output.
7. Recomendación de alcance: marcar como **decisión tomada**, no recomendación.
8. Sección nueva con la tabla CP1–CP5.
9. Sección nueva con la estrategia de tests unit/integration/anti-bug.
10. Sección 5 (prompt inicial) / checklist: eliminar las dos preguntas ya decididas (r7, scraping).

---

## 9. Próximo paso

Invocar `superpowers:writing-plans` con este diseño como input para producir el plan de
implementación detallado (con pasos, comandos, criterios verificables por paso).
