# Informe 01 — Segmentación por años

**Fecha:** 2026-06-25  
**Carpeta:** `euromillones-analyzer/`  
**Archivo fuente:** `run_approach_01_yearly_segmentation.py`  
**Datos:** `reports/informes/informe_01_segmentacion_anual.json`

---

## 🎯 Objetivo

Detectar si la distribución de números/estrellas **cambia entre períodos de tiempo**. Si hay cambios significativos entre bloques (e.g. 2004-2008 vs 2019-2023), sugiere un cambio de régimen en el bombo o en las reglas del juego.

---

## 📐 Metodología

1. Dividir los 1951 sorteos en 5 bloques temporales:
   - 2004-2008 (periodo fundacional)
   - 2009-2013 (antes del cambio de reglas 2011)
   - 2014-2018 (periodo estable)
   - 2019-2023 (COVID + cambio cap 2020)
   - 2024-2026 (periodo reciente, datos parciales)

2. Para cada bloque: test chi² por número y por estrella contra uniforme.

3. Test de **homogeneidad chi²** entre todos los bloques: ¿la distribución global es la misma?

4. Test adicional: comparación bloque 2024-2026 vs todo el resto (¿hay un cambio de régimen reciente?).

---

## 📊 Resultados

### Top desviaciones por bloque

**Bloque 2009-2013** (n=400, primer período completo post-2011):
- Número 4: +30% (p=0.058)
- Número 8: -30% (p=0.058)
- Estrella 12: -100% (p=3.3e-16) ← solo existía desde mayo 2011

**Bloque 2014-2018** (n=516):
- Número 22: -30.2% (p=0.030) ← ya mostraba sesgo negativo
- Número 17: +27.9% (p=0.045)
- Estrella 12: -47.7% (p=0.00001)

**Bloque 2019-2023** (n=522):
- Número 22: -33% (p=0.017) ← persiste el sesgo
- Número 4: -33% (p=0.017)
- Estrella 2: +24.1% (p=0.024)

**Bloque 2024-2026** (n=259, parcial):
- Número 38: -42.1% (p=0.032)
- Estrella 11: -30.5% (p=0.045)

### Test de homogeneidad entre bloques

| Elemento | chi² | dof | p-value | Significativo (p<0.001) |
|---|---|---|---|---|
| **Números** | 191.26 | 196 | 0.582 | ❌ NO (distribución estable) |
| **Estrellas** | 275.57 | 44 | **2.8e-35** | ✅ SÍ (cambia entre bloques) |

### Bloque 2024-2026 vs resto

| Elemento | chi² | p-value |
|---|---|---|
| Números | 52.6 | 0.337 (NO cambia) |
| **Estrellas** | 44.4 | **6.2e-6** (cambia) |

---

## 🎓 Conclusiones

1. **Los números son consistentes** entre bloques. La distribución de números no muestra cambios estructurales significativos a lo largo de 22 años.

2. **Las estrellas muestran cambios significativos entre bloques**, pero esto es **esperado**: en mayo 2011 se introdujeron las estrellas 10, 11 y 12 (antes solo había 9). Esto altera la comparación.

3. **El número 22 muestra un sesgo negativo persistente**: aparece en -30% en 2014-2018, -33% en 2019-2023. Es el único número con sesgo consistente en el tiempo.

4. **Cambio reciente (2024-2026)**: las estrellas muestran desviación significativa del histórico. Pero solo llevamos 259 sorteos en este bloque, lo que hace al test sensible a variaciones aleatorias.

---

## ⚠️ Advertencias

- Los bloques pequeños (2004-2008 con ~300 sorteos, 2024-2026 con 259) tienen **menos poder estadístico**.
- El cambio de reglas de mayo 2011 (introducción de 3 estrellas adicionales) es un **confounder** importante.
- El bloque 2024-2026 es parcial (solo 2.5 años) — hay que reevaluar cuando tengamos más datos.

---

## 📁 Entregables

- Script: `run_approach_01_yearly_segmentation.py`
- JSON con resultados detallados: `informe_01_segmentacion_anual.json`
