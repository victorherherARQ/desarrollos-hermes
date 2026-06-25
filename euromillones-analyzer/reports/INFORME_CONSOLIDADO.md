# 📊 INFORME CONSOLIDADO — Euromillones Analyzer (todos los acercamientos)

**Fecha:** 2026-06-25  
**Proyecto:** `euromillones-analyzer/`  
**Sorteos analizados:** 1951 (2004-02-13 a 2026-06-23)

---

## 🎯 Resumen ejecutivo

Hemos aplicado **6 acercamientos estadísticos diferentes** sobre los 1951 sorteos históricos de Euromillones para buscar patrones que se desvíen del azar genuino. **La conclusión consistente en todos ellos es que Euromillones se comporta como un sorteo genuinamente aleatorio.**

| # | Acercamiento | Resultado principal |
|---|---|---|
| 1 | Segmentación por años | Números consistentes; estrellas cambian (por 2011) |
| 2 | Ventanas móviles (rolling) | Suma media estable (rango 7.27, std 1.90) |
| 3 | Memoria y rachas (Markov) | Cero memoria detectable entre sorteos |
| 4 | Tests formales de aleatoriedad | Entropía 99%+ del máximo |
| 5 | Información mutua | MI ~0 entre números y entre sumas |
| 6 | Análisis bayesiano | **Número 22** es el único sesgo persistente |

**Único patrón superviviente**: el **número 22** sale consistentemente menos de lo esperado (-16% en train, -34% en test).

---

## 📁 Estructura de los informes

Todos los informes individuales están en `reports/informes/`:

1. [`informe_01_segmentacion_anual.md`](informes/informe_01_segmentacion_anual.md) — Chi² por bloque + homogeneidad entre bloques
2. [`informe_02_ventanas_moviles.md`](informes/informe_02_ventanas_moviles.md) — Rolling windows + t-test de tendencia
3. [`informe_03_markov_memoria.md`](informes/informe_03_markov_memoria.md) — Runs test + autocorrelación + Markov
4. [`informe_04_aleatoriedad.md`](informes/informe_04_aleatoriedad.md) — Chi² omnibus + KS + Bartels + entropía
5. [`informe_05_entropia_info_mutua.md`](informes/informe_05_entropia_info_mutua.md) — MI entre números + sumas
6. [`informe_06_bayesiano.md`](informes/informe_06_bayesiano.md) — Posterior Beta-binomial + validación

También hay:
- `reports/INFORME_FINAL.md` — informe inicial con el primer análisis
- `reports/backtest_resultados.json` — JSON del primer backtesting
- `data/euromillones.db` — SQLite con los 1951 sorteos

---

## 🔑 Hallazgo clave: el número 22

De **todos los acercamientos**, solo **un patrón real** sobrevive:

| Métrica | Valor |
|---|---|
| Apariciones en train (2004-2020) | 115 / 1379 sorteos = **8.34%** |
| Esperado en train | 137.9 (10% por uniforme) |
| Desviación train | **-16.6%** |
| Apariciones en test (2021-2026) | 38 / 572 sorteos = **6.64%** |
| Esperado en test | 57.2 |
| Desviación test | **-33.6%** |
| Posterior bayesiano | 99.94% prob p < 0.1 |

**El número 22 es el único elemento que consistentemente aparece menos de lo esperado**, tanto en train como en test, con una desviación real (no espuria).

**Pero ojo**: aunque el sesgo del 22 es real, su impacto en probabilidad de ganar es **ínfimo**. La probabilidad de acertar 5 números específicos es de ~1 en 2.118e9, y la diferencia entre jugar con 22 o sin él es marginal.

---

## 📊 Tabla resumen de los 6 acercamientos

| Acercamiento | Hipótesis nula | Resultado | Patrón superviviente |
|---|---|---|---|
| 1. Segmentación anual | Misma distribución entre bloques | p=0.58 (nums) / p=2.8e-35 (stars, por 2011) | — |
| 2. Ventanas móviles | Suma media estable | std=1.90, t-test p=0.051 | — |
| 3. Markov / memoria | Sorteos independientes | chi²=9.83, p=0.875 | — |
| 4. Aleatoriedad formal | Datos aleatorios | Entropía 99.93% (nums) | — |
| 5. Información mutua | I(A;B) = 0 | MI media 0.0007 bits | — |
| 6. Bayesiano | p = uniforme | 7 nums con sesgo creíble, **solo 22 persiste** | **Número 22** |

---

## 🎓 Conclusión global

**Euromillones es estadísticamente indistinguible de un sorteo aleatorio** a través de 6 acercamientos independientes. El único outlier real es el **número 22**, con un sesgo negativo persistente del 16-34%.

**Recomendación práctica**:
- **NO usar patrones para jugar** — la mejora marginal no compensa el coste del boleto.
- El número 22 podría evitarse (sale menos), pero la probabilidad de ganar con cualquier combinación es ~1 en 139.838.160, así que el cambio es **económicamente irrelevante**.
- **El estudio es valioso como ejercicio metodológico** — muestra cómo NO caer en trampas de "data dredging" y regresión a la media.

---

## 🛠️ Reproducibilidad

Todos los scripts son ejecutables desde la raíz del proyecto:

```bash
cd /home/vhdez/desarrollos-hermes/euromillones-analyzer
source venv/bin/activate

# Acercamiento 1: Segmentación por años
python3 run_approach_01_yearly_segmentation.py

# Acercamiento 2: Ventanas móviles
python3 run_approach_02_rolling_windows.py

# Acercamiento 3: Markov y memoria
python3 run_approach_03_markov_runs.py

# Acercamiento 4: Tests de aleatoriedad
python3 run_approach_04_randomness_tests.py

# Acercamiento 5: Entropía e información mutua
python3 run_approach_05_entropy_mi.py

# Acercamiento 6: Análisis bayesiano
python3 run_approach_06_bayesian.py
```

Cada script genera:
- Salida en consola con resumen
- JSON en `reports/informes/` con resultados detallados

---

## 📚 Documentación adicional

- `README.md` — cómo usar el proyecto
- `docs/fuentes_datos.md` — investigación de fuentes
- `reports/INFORME_FINAL.md` — primer informe (análisis básico + backtesting inicial)
- `src/` — código fuente modular con docstrings
- `tests/` — 23 tests, todos pasan
