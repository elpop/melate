# Análisis estadístico de Melate — Spec para Claude Code

Proyecto base: [`elpop/melate`](https://github.com/elpop/melate) (Perl + SQLite).
Este documento se escribió revisando el fork local `electroniccats/melate`; el código
relevante (esquema, parsing del CSV, lógica de descarga) es idéntico al upstream.
Objetivo: construir un módulo de **inferencia estadística** sobre el histórico de sorteos
que ya descarga el repo, separando claramente "predecir" (imposible) de lo que sí tiene
valor analítico o de EV.

Premisa rectora: **cada sorteo es estadísticamente independiente.** El módulo no busca
predecir números; busca (a) verificar si la lotería es justa, (b) demostrar empíricamente
que la predicción no funciona, y (c) cuantificar el único margen real de valor esperado.

---

## 1. Contexto técnico (prerrequisito para todo)

### Base de datos
- Ruta: `~/.melate/melate.db` (SQLite). Se genera/actualiza con `melate.pl -download`.
- El módulo nuevo **solo lee**; no toca la lógica de descarga ni la escritura.

### Cómo se obtienen los datos (verificado contra la fuente real)
El repo descarga un CSV histórico por producto, hace `diff` contra la versión previa para
quedarse con los renglones nuevos, y los inserta en SQLite. El CSV oficial tiene **dos
variantes** según el producto:

**Productos con bola adicional (`additional=1`: Melate, Melate Retro):**
```
NPRODUCTO,CONCURSO,R1,R2,R3,R4,R5,R6,R7,BOLSA,FECHA
40,4217,30,33,44,45,46,48,16,30500000,24/05/2026
```

**Productos sin bola adicional (`additional=0`: Revancha, Revanchita):**
```
NPRODUCTO,CONCURSO,R1,R2,R3,R4,R5,R6,BOLSA,FECHA
41,4217,30,33,44,45,46,48,30500000,24/05/2026
```

El parsing real en `melate.pl:349-368` distingue ambos casos por el valor de `additional`.

- `BOLSA` = monto acumulado del premio mayor (NO es número de ganadores).
- `FECHA` = formato `DD/MM/AAAA`.
- El código ya captura todas las columnas; **no se está descartando ningún dato disponible**.

**NOTA DE MANTENIMIENTO (importante):** las URLs en el repo apuntan a `pronosticos.gob.mx`,
pero la fuente viva migró a `loterianacional.gob.mx` (Pronósticos quedó absorbido por Lotería
Nacional). Mismo path: `https://www.loterianacional.gob.mx/Documentos/Historicos/Melate.csv`.
Puede seguir funcionando por redirección, pero si la descarga falla, el origen es este. El
módulo de stats no descarga (solo lee la DB), así que no le afecta directamente, pero conviene
anotarlo para mantener poblada la DB.

### Esquema relevante
```
products(id, name, range, balls, additional, url, filename)
results(id, product_id, draw, date_time, r1..r7, award)
```

Productos y parámetros:

| Producto    | id | range | balls | additional | notas               |
|-------------|----|-------|-------|------------|---------------------|
| Melate      | 40 | 56    | 6     | 1          | r7 = bola adicional |
| Revancha    | 41 | 56    | 6     | 0          | solo r1–r6          |
| Revanchita  | 34 | 56    | 6     | 0          | solo r1–r6          |
| Melate Retro| 30 | 39    | 6     | 1          | r7 = bola adicional |

### Gotchas que el código nuevo DEBE manejar
1. **Dos rangos distintos** (56 vs 39). Nada debe asumir 1–56 fijo. El `range` correcto
   debe leerse de la tabla `products` por producto, no hardcodearse.
2. **`additional`**: para id 40 y 30 existe `r7`. Decidir explícitamente si las pruebas de
   justicia usan solo r1–r6 (el sorteo principal) o incluyen r7. Recomendación: analizar
   r1–r6 como sorteo principal y r7 por separado, porque la bola adicional puede salir de
   un proceso distinto.
3. **Cómo está guardado `r7` para productos con `additional=0`**: el código (`melate.pl:366`)
   inserta **cadena vacía `''`**, no `NULL`, para Revancha y Revanchita. F0 (`db.py`) debe
   normalizar `''` → `None`/`NaN` al cargar a DataFrame, y nunca asumir que `r7 IS NULL` filtra
   correctamente esos productos. La forma robusta es ramificar por `additional` leído de
   `products`, no por el contenido de `r7`.
4. **`BOLSA` permite derivar rollovers (mejor de lo esperado)**: la columna no trae número de
   ganadores, pero su dinámica sí revela cuándo se ganó el premio mayor: **crece durante los
   acumulados y se reinicia a su piso cuando alguien gana**. Verificado en datos reales: el
   sorteo 4197 de Melate alcanza ~149.6 M y el 4198 cae a ~30 M (hubo ganador). Esto da un
   booleano "¿se ganó el premio mayor?" por sorteo, suficiente para la tarea 5 sin scrapear nada
   (ver F0.5). El conteo fino de ganadores por categoría existe pero solo en las páginas de
   resultados por sorteo, no en el CSV (ver tarea 13, opcional).
   **El piso debe estimarse empíricamente** del histórico de cada producto (mínimo recurrente),
   no fijarse. Valores publicados como referencia, NO para hardcodear: ~30 M Melate, ~20 M
   Revancha (provienen del reglamento de Lotería Nacional y pueden cambiar).
5. **Comparaciones múltiples**: probar 56 bolas a la vez infla los falsos positivos.
   Toda prueba por-bola debe llevar corrección (ver tarea 2).
6. **Tamaño del histórico**: el número de sorteos NO debe hardcodearse. Las cifras "~4,200"
   que aparecen en este documento son orientativas (consistentes con el CONCURSO 4217 mostrado
   arriba, ya que los sorteos se numeran secuencialmente desde 1); el conteo real se obtiene
   de la DB en F0.

### Stack sugerido
- Python 3.11+ (más cómodo para estadística que Perl; corre junto al repo sin tocarlo).
- `pandas`, `numpy`, `scipy.stats`, `statsmodels`, `matplotlib`.
- Lectura con `sqlite3` de stdlib.
- Estructura propuesta:
  ```
  stats/
    db.py          # capa de acceso: carga draws por producto a DataFrame
    rollover.py    # tarea F0.5: deriva flag de premio-ganado/rollover desde BOLSA
    fairness.py    # tareas 1,2,3,7,8,9
    backtest.py    # tarea 4
    behavior.py    # tarea 5
    multivariate.py# tarea 6
    drift.py       # tarea 10
    ingest.py      # tarea 13 (opcional): scraping de ganadores por categoría
    report.py      # genera reporte consolidado (markdown/HTML + gráficas)
    cli.py         # python -m stats --product melate --analysis chi2 ...
  ```
- Cada análisis: función pura que recibe un DataFrame de draws y devuelve resultados +
  objeto de figura. Reporte final que las orquesta.

---

## 2. Lista priorizada de análisis

Orden = relevancia + dependencias. Las **Fundamentales** habilitan al resto; constrúyelas
primero. Cada tarea trae criterio de aceptación.

### FUNDACIÓN (hacer primero — todo lo demás depende de esto)

**F0 · Capa de acceso a datos** (`db.py`)
Cargar los sorteos de un producto a un DataFrame normalizado (una fila por bola sorteada,
o matriz draw×bola), respetando `range` y `additional` leídos de la tabla `products`.
Normalizar `r7 = ''` → `None`/`NaN` (ver gotcha 3). Reportar el conteo real de sorteos cargados.
*Aceptación:* `load_draws("melate")` devuelve todos los sorteos con manejo correcto de r7 y
del rango; funciona para los 4 productos; para Revancha/Revanchita, `r7` queda como `NaN` en
todas las filas (no como cadena vacía).

**F0.5 · Derivar flag de premio-ganado / rollover desde `BOLSA`** (`rollover.py`)
A partir de la serie de `award` (BOLSA) por sorteo ordenada cronológicamente, marcar cada
sorteo con un booleano `jackpot_won` (≈ la bolsa se reinicia al piso en el sorteo siguiente)
y su complemento `rollover`. **Estimar el piso empíricamente por producto** (mínimo recurrente
de la serie); los valores publicados (~30 M Melate, ~20 M Revancha) son referencia para
sanity-check, no para hardcodear.

**Robustez requerida:** un simple "la bolsa cayó" sobre-cuenta ganadores cuando la bolsa baja
por motivos administrativos (sorteos especiales, ajustes). Detección robusta:
```
jackpot_won[k] := (BOLSA[k+1] ≤ piso_estimado × (1+ε))
                  AND (BOLSA[k]   ≥ piso_estimado × umbral)
```
con `ε` pequeño (p. ej. 0.05) para tolerar fluctuación del piso y `umbral` ≥ 1.2 para exigir
que sí hubiera acumulación previa real. También manejar: incrementos mínimos garantizados
entre sorteos sin ganador, sorteos especiales (bolsa anormalmente alta sin caída posterior),
y el último sorteo del histórico (no hay `k+1`).

*Aceptación:* serie booleana por sorteo + tasa global de rollover; validación visual contra la
serie de BOLSA en algunos tramos conocidos (p. ej. el reset del sorteo 4197→4198 en Melate);
reportar también cuántos sorteos quedan marcados como ambiguos (caída anómala que no cumple
ambas condiciones).
*Dependencia:* F0. **Habilita la tarea 5.** Es la pieza que vuelve la tarea 5 viable sin scraping.

---

### TIER 1 — Núcleo de inferencia de justicia

**1 · Chi-cuadrado de bondad de ajuste** `fairness.py`
Frecuencia observada de cada bola vs. esperada bajo uniforme. Estadístico + p-valor +
grados de libertad. Es la línea base. Resultado esperado: no se rechaza la uniformidad.
*Aceptación:* reporta χ², gl, p; gráfica de frecuencias observadas vs. banda esperada.
*Dependencia:* F0.

**2 · Corrección de comparaciones múltiples** `fairness.py` (transversal)
No es standalone: es un envoltorio para toda prueba por-bola (tareas 1 residual, 8, 10).
Implementar Bonferroni y FDR (Benjamini-Hochberg).
*Aceptación:* dada una lista de p-valores por bola, devuelve cuáles sobreviven a α tras
corrección; el reporte nunca presenta "bolas significativas" sin corregir.
*Dependencia:* se integra con 1 desde el inicio.

**3 · Simulación Monte Carlo** `fairness.py` (utilidad compartida)
Generar N loterías sintéticas justas para construir distribuciones nulas empíricas.
Sirve para validar χ², gaps y —sobre todo— como baseline aleatorio del backtest (tarea 4).
*Aceptación:* función que genera draws uniformes con los parámetros de un producto y
devuelve la distribución nula de cualquier estadístico que se le pase.
*Dependencia:* F0. **Habilita 4, 8.**

---

### TIER 2 — Lo interesante / con potencial original

**4 · Backtesting del feature `-weight`** `backtest.py`  ← **máximo valor pedagógico**
Reproducir el algoritmo de pesos del repo (suma de ocurrencias por segmento × nivel
decreciente, lo reciente pesa más). Walk-forward: en cada sorteo k, dejar que el algoritmo
proponga sus "números probables" usando solo datos ≤ k, y medir aciertos vs. selección
aleatoria, repetido sobre todo el histórico.
*Resultado esperado:* aciertos ≈ azar → demuestra empíricamente que el feature estrella no
predice. Cierra el círculo intelectual del proyecto.
*Aceptación:* curva/tabla de tasa de acierto del `-weight` vs. baseline Monte Carlo, con IC;
prueba de que la diferencia no es significativa.
*Dependencia:* F0, 3.

**5 · Selección consciente (rollovers vs. Poisson)** `behavior.py`  ← **potencial de ser original**
Detectar que los *jugadores* no eligen al azar (aunque el sorteo sí lo sea), vía exceso de
rollovers frente a lo que predice una Poisson bajo elección uniforme. Es el único margen de
EV real: combinaciones impopulares → menos premio compartido.
No conozco estudio de *conscious selection* sobre Melate → un mini-análisis aquí es
genuinamente nuevo, no una réplica. (Búsqueda hecha: existe muchísimo contenido comercial de
"números calientes/fríos" —frecuencias marginales, lo que el repo ya hace— pero NADA de
inferencia de selección consciente / exceso de rollovers sobre Melate. El terreno está libre.)
*Aceptación:* tasa de rollovers observada (de F0.5) vs. esperada bajo Poisson con elección
uniforme; si los datos lo permiten, modelo (1–p)α + βQ y test de α=0, β=1. Reportar el tamaño
del exceso de rollovers como evidencia de selección consciente.
**CAVEAT a interpretar (obligatorio en el reporte):** una fracción desconocida de jugadores usa
"selección automática" (Quick Pick), que SÍ es uniforme. Eso atenúa el exceso de rollovers
medible, sesgando la estimación hacia "menos selección consciente de la real". Por tanto el
resultado es una **cota inferior** del efecto, no una medida exacta. No sobrevender el hallazgo.
*Dependencia:* F0, **F0.5**. (Ya NO depende de scraping: el flag de rollover sale de `BOLSA`.
La versión enriquecida con conteo de ganadores por categoría es la tarea 13, opcional.)

**6 · Bayesiano: justicia con Dirichlet-multinomial** `fairness.py`  ← **el más elegante**
Prior Dirichlet sobre las probabilidades verdaderas de cada bola; posterior tras observar el
histórico; factor de Bayes entre "justa" vs. "sesgada". Da una distribución posterior por
bola en vez de un p-valor binario.
*Aceptación:* posterior con intervalos creíbles por bola; factor de Bayes reportado e
interpretado.
*Dependencia:* F0. (Independiente de 1, es alternativa moderna a ella.)

---

### TIER 3 — Estructura más profunda

**7 · Test multivariado de co-ocurrencia** `multivariate.py`  ← **el que más podría *encontrar* algo**
Matriz de co-ocurrencia (veces que salieron juntas las bolas i,j) vs. esperada bajo
**hipergeométrica multivariada** (6-de-56 induce correlación negativa calculable). Captura
sesgo físico que las frecuencias marginales (tarea 1) se pierden.
*Aceptación:* heatmap de desviaciones estandarizadas; prueba global de ajuste a la
hipergeométrica.
*Dependencia:* F0.

**8 · Análisis de gaps (K-S vs. geométrica)** `fairness.py`
Distribución de "cada cuántos sorteos reaparece cada número"; bajo independencia es
geométrica. Test de Kolmogórov-Smirnov.
*Aceptación:* distribución de gaps observada vs. geométrica teórica + estadístico K-S/p.
*Dependencia:* F0, 3 (banda nula por Monte Carlo).

**9 · Test de rachas y autocorrelación serial** `fairness.py`
Detectar dependencia entre sorteos consecutivos (runs test; autocorrelación de indicadores
de aparición por bola).
*Aceptación:* runs test global + autocorrelaciones con bandas de confianza.
*Dependencia:* F0.

**10 · Detección de cambio / deriva temporal** `drift.py`
Las máquinas y balotas se reemplazan/desgastan: un sesgo puede aparecer y desaparecer,
invisible al promediar todo el periodo. CUSUM o test de Pettitt sobre frecuencias por
ventana temporal.
*Aceptación:* identifica change-points candidatos por bola (con corrección de tarea 2);
gráfica de frecuencia móvil.
*Dependencia:* F0, 2.

---

### TIER 4 — Especializado / opcional

**11 · Baterías de aleatoriedad de calidad criptográfica** (externo)
Serializar la secuencia de sorteos a un bitstream y pasarla por NIST SP 800-22, dieharder o
TestU01. "Examen serio" de RNG aplicado a una lotería real.
*Aceptación:* reporte de qué tests pasa/falla.
*Dependencia:* F0 + herramientas externas. Encaje algo forzado (serialización no trivial);
baja prioridad.

**12 · Wheeling / covering designs** (tangente)
Diseño combinatorio para *garantizar* aciertos parciales con un set de boletos. **No es
inferencia** y no mejora la probabilidad del premio mayor. Incluir solo como apéndice
opcional; es el menos relevante para el hilo estadístico.
*Dependencia:* F0.

**13 · Ingesta de ganadores por categoría (scraping)** `ingest.py` (opcional, habilita la v2 de la tarea 5)
Pronósticos/Lotería Nacional publica por sorteo el desglose completo: número de ganadores y
premio en cada categoría (6 naturales, 5+adicional, 5, 4+adicional, 4, 3+adicional, 3, 2…).
Scrapear esto daría la **distribución completa del número de ganadores**, no solo el booleano
de rollover, y permitiría la versión fuerte de la tarea 5 (comparar la distribución observada
de ganadores contra la Poisson/binomial esperada bajo juego uniforme, y estimar sobredispersión).
*Aceptación:* tabla por sorteo×categoría con nº de ganadores y premio, persistida en una tabla
nueva (p. ej. `winners`) sin tocar las tablas existentes.
*Dependencia:* F0. **Costo/riesgo:** una petición por sorteo (~4,200), páginas históricas viejas
pueden no existir todas, y el formato puede cambiar. Frágil; hacerlo solo si se quiere la v2.

---

## 3. Recomendación de alcance para el primer pase

Para un entregable redondo y honesto, el camino mínimo con mejor relación valor/esfuerzo es:

```
F0  →  1 + 2 + 3  →  4  →  F0.5  →  5
```

Eso cuenta la historia completa: **"predecir es imposible (1, 4) y aquí está lo único que sí
mueve la aguja (5)"**, con la base inferencial sólida (1–3) y el desmentido empírico del
propio feature del repo (4). La tarea 5 ahora es plenamente viable gracias a F0.5 (rollover
derivado de `BOLSA`). Las tareas 6–10 son ampliaciones naturales; 11–13 opcionales (13 solo
si se quiere la versión fuerte de la 5 con conteo real de ganadores).

---

## 4. Resultados esperados e interpretación

El valor del proyecto está en el **contraste** entre tres baldes. Esta sección es el patrón
contra el cual Claude Code debe contrastar su propia salida: **si un resultado se desvía de lo
esperado aquí, lo primero a sospechar es el código, no la lotería.**

### Balde 1 — Justicia (tareas 1, 6, 7, 8, 9, 10): esperado = "aburrido" (NO rechazar el null)
- **Chi-cuadrado (1):** p > 0.05; χ² cercano a sus gl (55 para rango 56; 38 para Retro). Cada
  bola debería aparecer ≈ N_sorteos × 6/range veces (p. ej. ~450 si hay ~4,200 sorteos en
  Melate — el N real se lee de la DB en F0, no se asume), con fluctuaciones dentro de banda
  pero sin desviación sistemática.
- **Bayesiano (6):** posterior de cada bola concentrado en 1/range; intervalos creíbles
  solapando la uniforme; factor de Bayes a favor de "justa".
- **Co-ocurrencia (7):** matriz consistente con la hipergeométrica multivariada; sin pares
  sobre/sub-representados más allá del ruido.
- **Gaps (8), rachas/autocorrelación (9), deriva (10):** consistentes con independencia; K-S no
  significativo, autocorrelaciones dentro de bandas, ningún change-point que sobreviva la
  corrección (tarea 2).

Resultado ideal del balde: **la lotería es indistinguible de un sorteo justo.**

### Balde 2 — Backtest del `-weight` (tarea 4): esperado = el null más satisfactorio
Tasa de acierto del algoritmo de pesos **estadísticamente idéntica al azar**. El número
esperado de aciertos al elegir 6 de 56 es 6 × 6/56 ≈ **0.64 aciertos por sorteo**; el `-weight`
debe caer ahí, con su diferencia vs. el baseline Monte Carlo dentro del IC.
Resultado ideal: **el feature estrella del repo no predice nada.**

### Balde 3 — Selección consciente (tarea 5): esperado = SÍ rechazar el null (resultado positivo)
Único análisis donde lo ideal es significativo: tasa de rollovers observada **> ** la que
predice una Poisson bajo juego uniforme. Los jugadores se amontonan en combinaciones populares
→ sube la probabilidad de que nadie acierte el premio mayor. La literatura lo encuentra en todos
los países; lo ideal es replicarlo en Melate. Por el Quick Pick (ver caveat de la tarea 5), el
efecto medido es **cota inferior**: basta con que la dirección (exceso de rollovers) sea clara.

### La narrativa ideal completa
> El sorteo es demostrablemente justo (balde 1) **y** el método de predicción del propio repo
> demostrablemente no sirve (balde 2) — **pero** los jugadores demostrablemente no eligen al azar
> (balde 3), y eso es lo único con consecuencia real sobre el valor esperado.

### Señales de que es un BUG, no un hallazgo (auto-revisión obligatoria)
- **Chi-cuadrado fuertemente significativo** → casi seguro error de binning, mal manejo de r7, o
  desajuste de rango (56 vs 39). Revisar F0 antes de concluir sesgo físico.
- **El backtest del `-weight` "gana"** → señal casi inequívoca de *data leakage* (usar datos > k
  al predecir el sorteo k). Poder predictivo real sería extraordinario; un bug temporal es
  muchísimo más probable. Auditar la ventana walk-forward.
- **Cero exceso de rollovers en la tarea 5** → revisar primero la derivación del flag desde
  `BOLSA` en F0.5 (¿bien detectados los resets al piso?) antes de concluir que no hay selección
  consciente.

### Recordatorios de honestidad estadística (deben estar en el reporte)
- "No rechazar" en el balde 1 **no prueba** que la lotería sea perfecta: con el orden de
  ~4,200 sorteos hay potencia para sesgos grandes, pero uno pequeño puede pasar desapercibido.
  Reportar el tamaño de efecto detectable junto con el p-valor, y reportar también el N real
  del histórico cargado.
- Con muchas pruebas sobre varios productos, **ver 1–2 resultados "significativos" sin corrección
  es lo esperado por azar.** Por eso la corrección de comparaciones múltiples (tarea 2) no es
  opcional, y el reporte nunca debe presentar bolas "significativas" sin corregir.

---

## 5. Prompt inicial para pegar en Claude Code

> Estoy trabajando sobre el repo `elpop/melate` (Perl + SQLite), que descarga el histórico de
> la lotería mexicana Melate/Revancha/Revanchita/Retro a `~/.melate/melate.db`. Quiero añadir
> un módulo nuevo en Python (sin tocar el código Perl) que haga **inferencia estadística** sobre
> ese histórico. El esquema de la DB y los parámetros por producto están en el archivo
> `melate-stats-spec.md` que te adjunto — léelo completo antes de empezar; presta especial
> atención a la sección "Gotchas" (dos rangos distintos, bola adicional r7, y que el rollover
> del premio mayor se DERIVA de la columna `BOLSA`, no viene como número de ganadores).
>
> Empieza por la FUNDACIÓN (F0: capa de acceso `db.py`) y luego implementa las tareas 1, 2 y 3
> del Tier 1, en ese orden, con sus criterios de aceptación. Usa pandas, numpy, scipy.stats,
> statsmodels y matplotlib. Sigue la estructura de carpetas propuesta en el spec. Antes de
> escribir cada análisis, confírmame el enfoque estadístico en una línea. No implementes nada
> que prediga números futuros: el objetivo es verificar justicia y demostrar que la predicción
> no funciona.
>
> Contrasta cada resultado contra la sección "Resultados esperados e interpretación" del spec.
> Si algún resultado se desvía de lo esperado (p. ej. chi-cuadrado muy significativo, o el
> backtest del `-weight` "ganando"), trátalo primero como sospecha de bug —revisa binning,
> manejo de r7, rango, y data leakage— antes de reportarlo como hallazgo.
>
> Cuando F0 + tareas 1–3 estén listas y probadas contra la DB real, paramos para revisar antes
> de seguir con la tarea 4 (backtesting del feature `-weight`) y luego F0.5 + tarea 5.

### Checklist de lo que Claude Code necesita tener a mano
- [ ] Este archivo `melate-stats-spec.md`.
- [ ] Acceso a una `melate.db` poblada (correr `melate.pl -download` una vez, o copiar la DB).
      Si la descarga falla, revisar la nota de mantenimiento: la fuente migró a
      `loterianacional.gob.mx`.
- [ ] Confirmar Python ≥ 3.11 y poder instalar las librerías del stack.
- [ ] Decisión tuya sobre r7: ¿análisis principal solo r1–r6? (recomendado sí).
- [ ] Decisión tuya: ¿se quiere la tarea 13 (scraping de ganadores) para la versión fuerte de
      la tarea 5, o basta con el rollover derivado de `BOLSA` (F0.5)?
