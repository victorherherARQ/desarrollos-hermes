# Informe 03 — Memoria y rachas (Markov + runs test)

**Fecha:** 2026-06-25  
**Carpeta:** `euromillones-analyzer/`  
**Archivo fuente:** `run_approach_03_markov_runs.py`  
**Datos:** `reports/informes/informe_03_markov_memoria.json`

---

## 🎯 Objetivo

Determinar si hay **memoria** entre sorteos consecutivos. Si la hipótesis nula (sorteos independientes) es cierta, los siguientes tests deben NO rechazar H0:

1. **Runs test**: ¿los números "calientes" y "fríos" se agrupan o alternan al azar?
2. **Autocorrelación de suma** con lags 1-10
3. **Autocorrelación binaria por número** en lag 1
4. **Markov orden 1** sobre la suma categorizada

---

## 📐 Metodología

- **Runs test**: secuencia binaria por número (1=aparece, 0=no aparece). Compara número de rachas observadas vs esperado bajo aleatoriedad. Estadístico Z.
- **Autocorrelación de suma**: correlación de Pearson entre suma_t y suma_{t+lag}, lags 1 a 10.
- **Autocorrelación por número**: cov(seq[:-lag], seq[lag:]) / var(seq) para cada número.
- **Markov orden 1**: categoriza la suma en 5 bins (quintiles) y aplica chi² de independencia sobre la tabla de transiciones.

---

## 📊 Resultados

### Runs test por número

| Elemento | Rachas observadas | Rachas esperadas | z-stat | p-value | Patrón |
|---|---|---|---|---|---|
| **6** | 363 | 347.2 | +2.02 | 0.044 | Agrupación |
| 30 | 331 | 350.4 | -2.46 | 0.014 | **Alternancia** |
| 33 | 326 | 311.4 | +2.08 | 0.037 | Agrupación |
| 41 | 316 | 331.0 | -2.02 | 0.044 | **Alternancia** |

**Total con patrón (p<0.05): 4 / 50** (esperado por azar: 2.5). Marginalmente más de lo esperado.

### Autocorrelación de la suma (lags 1-10)

| Lag | Autocorrelación | z-stat | p-value | Significativo |
|---|---|---|---|---|
| 1 | 0.0173 | 0.76 | 0.446 | ❌ NO |
| 2 | 0.0112 | 0.49 | 0.621 | ❌ NO |
| 3 | -0.0194 | -0.86 | 0.392 | ❌ NO |
| 4 | -0.0159 | -0.70 | 0.483 | ❌ NO |
| 5 | -0.0329 | -1.45 | 0.147 | ❌ NO |
| 6 | 0.0158 | 0.70 | 0.486 | ❌ NO |
| 7 | 0.0012 | 0.05 | 0.958 | ❌ NO |
| 8 | 0.0105 | 0.46 | 0.642 | ❌ NO |
| 9 | 0.0347 | 1.53 | 0.126 | ❌ NO |
| 10 | 0.0252 | 1.11 | 0.267 | ❌ NO |

**Ningún lag es significativo.** La suma del sorteo anterior **no predice** la del siguiente.

### Autocorrelación binaria por número (lag 1)

| Métrica | Valor |
|---|---|
| Autocorrelación media | **-0.0001** |
| Rango | [-0.050, 0.056] |

Top 5 con más autocorrelación positiva (números que "tienden a repetirse" en el siguiente sorteo):

| Número | Apariciones | Autocorrelación |
|---|---|---|
| 30 | 194 | +0.0555 |
| 47 | 181 | +0.0438 |
| 41 | 182 | +0.0432 |
| 28 | 186 | +0.0431 |
| 39 | 191 | +0.0423 |

Top 5 con más autocorrelación negativa (números que "alternan" — si sale, no sale al siguiente):

| Número | Apariciones | Autocorrelación |
|---|---|---|
| 33 | 170 | -0.0500 |
| 6 | 192 | -0.0457 |
| 29 | 217 | -0.0418 |
| 26 | 204 | -0.0402 |
| 25 | 204 | -0.0402 |

**Las autocorrelaciones son extremadamente bajas** (todas < 6%). Bajo independencia, esperaríamos desviaciones aleatorias del mismo orden.

### Markov orden 1 sobre la suma categorizada (5 bins)

| Métrica | Valor |
|---|---|
| Chi² de independencia | 9.83 |
| p-value | **0.8754** |
| ¿Hay memoria? | ❌ NO |

---

## 🎓 Conclusiones

1. **No hay memoria detectable** entre sorteos consecutivos. Los 4 números con runs test significativo (6, 30, 33, 41) están **dentro del rango esperado por azar** (esperados 2.5, observados 4).

2. **La suma del sorteo N no predice la del N+1** en ningún lag (1-10). Todos los p-values > 0.12.

3. **La autocorrelación por número es esencialmente cero** (media -0.0001). Las desviaciones individuales son del orden del 5%, totalmente compatibles con azar.

4. **Markov orden 1 sobre la suma** da chi²=9.83 con p=0.875 → confirma independencia total entre sumas consecutivas.

---

## ⚠️ Advertencias

- Los 4 números con runs test significativo podrían ser **falsos positivos** esperados: con 50 tests y umbral 0.05, esperaríamos 2.5 significativos por azar.
- **El test de runs es sensible al tamaño de bloque**: se podría refinar con long-run runs o análisis espectral.

---

## 📁 Entregables

- Script: `run_approach_03_markov_runs.py`
- JSON con resultados detallados: `informe_03_markov_memoria.json`
