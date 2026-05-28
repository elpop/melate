# Auditoría independiente — módulo `stats/` vs design 2026-05-28

**Branch:** `feat/stats-v1` @ `e76317b` (17 commits, no 16 — el `gitStatus` del prompt iba un commit por detrás).
**Reviewer no vio la implementación; sí leyó el design doc, el plan y el spec original.**

---

## CRÍTICOS

### C-1. El `report/melate-stats-v1/report.md` comiteado está obsoleto y miente sobre el estado del v1.

El usuario me pidió: *"Lee report/melate-stats-v1/report.md y verifica que no aparezca el banner ATENCIÓN (todo debería coincidir con el spec)"*. Cumple esa lectura literal: **no aparece el banner**, las 3 secciones (chi² r1..r6, backtest, rollover) están en ✅.

Pero ese archivo fue generado **antes** de `e76317b stats(cli): chi-square for r7 additional ball`. La regeneración con el código actual da:

```
> ## ⚠️ ATENCIÓN
> - **Chi-square goodness-of-fit (r7 additional ball)**: stat=73.34, dof=55, p=0.0498
```

Es decir: con el código en `HEAD`, **el reporte v1 actualmente sale con bandera roja** sobre r7 (p=0.0498 < 0.05). El report.md guardado no refleja eso porque no se regeneró tras añadir el análisis de r7. Cualquiera que mire sólo ese MD se va a llevar una impresión equivocada del estado del v1. La regla `report/` está en `.gitignore` (acción correcta), pero **el archivo local que sí existe en disco no refleja el código actual** — borrar el directorio y regenerar, o decidir explícitamente si r7 debe estar en v1.

### C-2. `derive_jackpot_won` interpreta `award=0` (dato faltante) como reset al piso, lo que produce wins espurias.

`estimate_floor` sí filtra `award > 0` (correcto, F-1 abajo). Pero `derive_jackpot_won` itera sobre la serie **sin filtrar 0s**:

```python
# rollover.py:69-72
next_low = award.iloc[k + 1] <= floor * (1 + eps)   # 0 <= 31.5M → True
curr_high = award.iloc[k] >= floor * threshold      # 190M >= 36M → True
...
if next_low and curr_high: jackpot.iloc[k] = True
```

Con la DB real (Melate, post-filtro 2008-01-01), hay 3 filas con `award=0` (draws 2120, 2142, 2234). Verifiqué los vecinos:

| draw | award[k] | award[k+1] | award[k+2] | resultado actual | correcto |
|---|---|---|---|---|---|
| 2141 | 128M | **0** | 30M | jackpot_won=True | True (por suerte: el next-next confirma) |
| 2233 | 190M | **0** | 213M | jackpot_won=True | **False** (el premio siguió subiendo) |

Es un **bug real**: la draw 2233 está marcada como ganada cuando objetivamente no lo fue. No es flag *ambiguous* (porque `curr_high=True`), así que pasa silencioso por el sanity check del 5%.

**Impacto cuantitativo:** ~1-2 wins espurias sobre 56 detectadas (≈2-3%). El `observed_rollover_rate=0.974` cambia ~0.001 al corregir. **No invalida** la conclusión del balde 3 (ratio > 1 a todo N) — por eso lo dejo como CRÍTICO de correctness pero no como "invalida resultado del reporte". Acción mínima: filtrar `award>0` también en `derive_jackpot_won`, o marcar `ambiguous=True` cuando `award[k+1]==0`.

---

## IMPORTANTES

### I-1. El reporte NO incluye la sanity-band del χ² aunque el spec la exige explícitamente.

Spec §5 (chi² acceptance): *"χ² dentro de `[gl − 2√(2·gl), gl + 2√(2·gl)]` como sanity (≈95% del nulo). **La banda no sustituye al p-valor; ambos van al reporte**."*

`stats/cli.py:26` solo emite `f"stat={res.stat:.2f}, dof={res.dof}, p={res.p_value:.4f}"`. Banda nunca calculada ni mostrada.

Esto importa **especialmente para r7**: con gl=55, la banda es [34.0, 76.0]. El observado `stat=73.34` está **dentro** de la banda — la falla aparente de p=0.0498 es exactamente el tipo de caso donde la banda da contexto ("estás dentro del 95% del nulo, no entres en pánico"). Sin la banda, el banner ATENCIÓN se ve más alarmante de lo que realmente es.

### I-2. No se aplica corrección de comparaciones múltiples a los dos χ² del reporte (`r1..r6` + `r7`).

`fairness.correct_pvalues` está implementada y testeada, pero **nunca invocada** desde el CLI/reporte. Con 2 tests de χ² en paralelo (r1..r6 y r7) y umbral nominal α=0.05, la probabilidad familywise de un falso positivo sube. La falla actual de r7 (p=0.0498) sobrevive sin corregir, pero con Bonferroni a 2 tests (α=0.025) **dejaría de fallar** (p=0.0498 > 0.025) — exactamente el escenario que la spec §5 / tarea 2 anticipa con *"Transversal: cualquier prueba por-bola la aplica antes de reportar"*.

Esto se conecta con C-1: el banner que aparece hoy probablemente **no debería estar ahí** si se aplicara la corrección que la misma codebase ya implementó.

### I-3. La rama informa "5 integration tests", realidad son 7.

```
test_backtest::test_weight_walkforward_melate_real_does_not_beat_random
test_behavior::test_rollover_excess_melate_real_lower_bound
test_db::test_load_draws_real_db_matches_count
test_db::test_load_draws_default_filters_to_current_format_era
test_e2e::test_full_pipeline_on_real_melate
test_fairness::test_chi_square_melate_real_does_not_reject
test_rollover::test_derive_jackpot_won_real_melate
```

Todos pasan, no hay skips. Sólo es un mismatch con el prompt (probable: el plan original listaba 5 y se añadieron `default_filters_to_current_format_era` + `e2e` después). No es bug; mencionarlo por si se está usando el conteo para algo.

### I-4. `simulate_null` (tarea 3) y `correct_pvalues` (tarea 2) son código vivo testeado pero no surfaceado en el reporte.

Ambas funciones existen y pasan tests, pero el CLI no las invoca. El spec §5 las incluye explícitamente en el data flow del v1. Decisión consciente o gap — vale la pena marcar el alcance: el reporte actual entrega "3 baldes pero sin la maquinaria estadística de tarea 2+3 que el design listó". Si la intención fue cortarlas de v1, debería estar explicitado en el design (ahora dice lo contrario).

---

## MENORES

### M-1. Cosmético: `N=50,000,000.0` en el reporte de behavior.
`per_N["N"]` es `int64` en el DataFrame, pero `iloc[-1]` devuelve una Series mixta donde N se promueve a `numpy.float64`. El `:,` format del CLI sale con `.0` colgante. Fix de 1 línea: `int(largest['N'])` o `f"{int(largest['N']):,}"` en `cli.py:75`.

### M-2. Estilo: `(won == False).sum()` en `behavior.py:30`.
Flake8/pep8 (E712) recomienda `(~won).sum()` o `(won == False).sum()` con `# noqa`. Funcionalmente correcto (la serie ya es bool tras `dropna()` sobre un `Series[object]`), pero noisy en lint.

### M-3. Estilo: `is True or == True` doble en `test_rollover.py:51`.
```python
assert df.loc[2, "jackpot_won"] is True or df.loc[2, "jackpot_won"] == True
```
Cinto y tirantes — el dtype es `object` así que `is True` debería bastar. No molesta a ningún lint que importe, pero deja huella de "el autor no estaba seguro de qué tipo iba a salir".

### M-4. `_db_path()` se abre dos veces en `load_draws` (uno para metadata, otro para results).
Una sola conexión + dos `execute` haría la misma cosa con menos ceremonia. No afecta correctness.

### M-5. `report.py` no llama `plt.close(fig)` después de `savefig`.
Para un run de 3-4 figuras es trivial; en un loop de productos podría acumular memoria de matplotlib. Lo menciono porque CP5 (opcional) podría iterar.

### M-6. `cli.py` declara `--analyses rollover` en `ANALYSES` pero ningún branch lo maneja.
Solo se dispatcha `chi2`, `backtest`, `behavior`, `all`. Pedir `--analyses rollover` corre sin error pero no produce nada.

---

## VERDE (cosas bien hechas)

- **V-1. Anti-leakage en backtest funciona.** `walk_forward_hits` raises `DataLeakageError` con history que contiene `draw >= target.draw`. Equivalente al `max < k` que pide el spec, y la chequeo positivo: el test `test_walk_forward_raises_on_duplicate_draws` lo cubre. Sobre la DB real (`since='1900-01-01'` o filtrada) no dispara — load_draws garantiza orden ascendente único por `(product_id, draw)` (índice único en SQLite).
- **V-2. Separación r1-r6 vs r7 es estricta.** `db.py:140` construye `draws_long` solo desde `ball_cols = [f"r{i}" for i in range(1, n_balls+1)]`; r7 nunca se mete. `r7_series` solo se materializa si `has_additional`. La r7 viaja por su propio canal (`_run_chi2_r7`) cuando el CLI corre `chi2`.
- **V-3. `DEFAULT_SINCE` filtra correctamente a la era homogénea.** Verificado contra la DB real: 4218 → 2124 sorteos para Melate, max ball post-filtro = 56, fecha mínima ≥ 2008-01-01. Es lo que el design pide. El sanity test `test_load_draws_default_filters_to_current_format_era` lo blinda.
- **V-4. Normalización de `r7=''` → `Int64`.** `pd.to_numeric(..., errors='coerce').astype('Int64')` aplicado siempre, no solo cuando `has_additional`. Tests `test_r7_normalized_to_int64_nullable_for_revancha` y `_for_melate` cubren ambos lados.
- **V-5. `estimate_floor` usa moda en lugar de min — desviación del spec, pero justificada.** El spec §5 dice "usar min, warning si moda discrepa". El código hace lo contrario: usa moda, warning si min discrepa. Empíricamente, **moda es más robusta** (un solo `award=13000` outlier ya ensuciaría min); y `estimate_floor` además filtra `award > 0`, lo que elimina los 173 filas pre-2008 con award=0. La desviación está testeada explícitamente (`test_estimate_floor_warns_when_min_and_mode_disagree`) y produce el resultado correcto sobre la DB real (30M). Tiene sentido — solo recomendaría actualizar el texto del spec para reflejar la decisión.
- **V-6. `award=13000` (draw 1978, 2006) no contamina nada por default.** Pre-2008 → filtrado por `DEFAULT_SINCE`. Si alguien pasa `since='1900-01-01'`, la moda de la cola inferior sigue siendo 30M y solo dispararía un `FloorEstimateWarning`.
- **V-7. `award=0` en 2007 (datos faltantes) no afecta `estimate_floor`.** El filtro `valid = award[award > 0]` se aplica antes de calcular min/moda. (Pero ojo: el mismo cuidado **no** se replica en `derive_jackpot_won` → bug C-2.)
- **V-8. Sin valores hardcoded en código de producción.** `range_`, `n_balls` viajan parametrizados en todos los módulos de `stats/`. Los 56/6 que aparecen están exclusivamente en `tests/` y `conftest.py` como dato de fixture, lo cual es correcto.
- **V-9. Seeds fijos en todos los tests con aleatoriedad** (`default_rng(0|1|2|7|42|123)`). El único test con asunción estadística sin seed-pinning (`test_simulate_null_two_seeds_give_indistinguishable_distributions`) usa n=2000 y KS, robusto.
- **V-10. 44/44 unit tests + 7/7 integration tests verdes.** Resultados estadísticos sobre Melate real exactamente como el spec anticipa:
  - χ² r1..r6: p=0.6719 ✅
  - backtest -weight: rate=0.645 ≈ baseline=0.643, p=0.9082 ✅
  - rollover ratio @ N=50M: 4.541 ✅
  - ambiguous rate: 0.003 < 5% ✅
  - floor estimate: 30M ✅
- **V-11. ATENCIÓN banner SÍ funciona como el spec lo pide** (`report.py:24-32`): genera lista de mismatches y bloquea la lectura inocente. Probado en `test_build_report_flags_mismatch_with_attention_banner` y disparado en vivo por r7.

---

## Resumen ejecutivo

V1 está **mucho más cerca de mergeable de lo que la suite de tests sugiere**. Las tres conclusiones del design (lotería justa, `-weight` no predice, exceso de rollover ≥ 4×) son sólidas y replicables.

Pero hay un **gap importante entre lo que el reporte impreso muestra y el estado actual del código**:

1. **Antes de mergear:** regenerar `report/melate-stats-v1/report.md` con el código actual (C-1), decidir si la falla marginal de r7 es real o artefacto de no-corrección (I-2), y arreglar el bug de `award=0` en `derive_jackpot_won` (C-2).
2. **Antes de presentar a otro humano:** añadir la sanity-band del χ² al reporte (I-1) — sin ella el banner ATENCIÓN sobre r7 se ve peor de lo que es.
3. **Para la próxima iteración:** aplicar `correct_pvalues` cuando haya ≥2 χ², limpiar el `.0` cosmético, decidir qué hacer con `simulate_null` que está sin uso.
