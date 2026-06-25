# Informe 02 — Ventanas móviles (rolling windows)

**Fecha:** 2026-06-25  
**Carpeta:** `euromillones-analyzer/`  
**Archivo fuente:** `run_approach_02_rolling_windows.py`  
**Datos:** `reports/informes/informe_02_ventanas_moviles.json`

---

## 🎯 Objetivo

Detectar **cambios de régimen** deslizando una ventana de 200 sorteos (~2 años) por toda la serie. Si la suma media o las frecuencias cambian mucho entre ventanas, sugiere que el comportamiento del bombo evoluciona con el tiempo.

---

## 📐 Metodología

1. **Window size:** 200 sorteos (~2 años)
2. **Step:** 50 sorteos (~6 meses)
3. Para cada ventana: calcular la frecuencia de cada número/estrella y la suma media
4. Análisis de tendencia: t-test de Student sobre la suma media (primera mitad de ventanas vs segunda mitad)
5. Top 5 ventanas con mayor desviación chi²

---

## 📊 Resultados

### Número total de ventanas analizadas

**36 ventanas** distribuidas a lo largo de 22 años.

### Top 5 ventanas con mayor desviación en NÚMEROS

| Fecha inicio | Fecha fin | Número | Desviación | chi² |
|---|---|---|---|---|
| 2005-01-28 | 2008-11-28 | **50** | **+80.0%** | 12.80 |
| 2022-08-23 | 2024-07-19 | 35 | +70.0% | 9.80 |
| 2006-01-20 | 2009-11-06 | 50 | +65.0% | 8.45 |
| 2012-07-17 | 2014-06-13 | 44 | +65.0% | 8.45 |
| 2021-03-16 | 2023-02-10 | 21 | +65.0% | 8.45 |

### Top 5 ventanas con mayor desviación en ESTRELLAS

Los mayores picos en estrellas (chi²=33.33) corresponden a los años 2004-2010, donde las estrellas 10, 11 y 12 **no existían todavía** (introducidas en mayo 2011). Esto NO es un patrón, es un artefacto histórico.

### Evolución de la suma media

| Métrica | Valor |
|---|---|
| Suma media global | 127.49 |
| **Rango de sumas medias por ventana** | 123.86 - 131.13 |
| **Desviación estándar entre ventanas** | **1.90** (extremadamente bajo) |

**Diferencia entre la suma mínima y máxima de las ventanas: solo 7.27** (sobre una media de 127.49 → variación del 5.7%).

### Test de tendencia (t-test)

| Test | t-stat | p-value | Significativo |
|---|---|---|---|
| Primera mitad vs segunda mitad | -2.024 | 0.0509 | ❌ NO (marginal) |

---

## 🎓 Conclusiones

1. **La suma media es EXTREMADAMENTE estable** a lo largo del tiempo. La desviación estándar entre ventanas es solo 1.90, y el rango total es de 7.27 sobre una media de 127.49.

2. **No hay tendencia lineal** significativa: el t-test entre la primera y la segunda mitad de ventanas da p=0.0509 (marginal, no concluyente).

3. **Los "picos" de desviación son esporádicos** y siempre en ventanas individuales — son ruido, no patrón. Por ejemplo, el número 50 tuvo +80% en 2005-2008 pero volvió a la media después.

4. **No se detecta cambio de régimen**: el comportamiento global del bombo es estable.

---

## ⚠️ Advertencias

- El top 5 de ventanas desviadas muestra el **número 50** apareciendo dos veces en los primeros años. Pero con chi² máximo de 12.80 sobre 200 sorteos, esto es esperable por azar (1 entre 36 ventanas肯定会 tenga una desviación alta por casualidad).
- El p-value marginal de 0.0509 podría alcanzar significancia con más datos, pero **no es concluyente**.
- Esta técnica es sensible al tamaño de ventana: ventanas más pequeñas serían más ruidosas, ventanas más grandes ocultarían tendencias.

---

## 📁 Entregables

- Script: `run_approach_02_rolling_windows.py`
- JSON con resultados detallados: `informe_02_ventanas_moviles.json`
