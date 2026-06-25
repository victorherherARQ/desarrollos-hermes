# 📊 INFORME FINAL — Euromillones Analyzer

**Fecha del análisis:** 2026-06-24  
**Proyecto:** `euromillones-analyzer/`  
**Objetivo:** Detectar patrones estadísticamente significativos en los resultados históricos de Euromillones y validarlos con backtesting riguroso.

---

## 🎯 Resumen ejecutivo

**Pregunta del usuario:** ¿Hay patrones en los sorteos de Euromillones que se repitan más de lo esperado por azar, y se confirman al dividir los datos en entrenamiento y test?

**Respuesta corta:** No se han encontrado patrones robustos. Lo que parecía significativo mirando los 1951 sorteos completos (sobre todo la estrella 12 con un -46.5%) **no sobrevive al backtesting**. Solo 3 de 6 patrones sobreviven al test temporal, y todos ellos son estrellas con desviaciones pequeñas en el conjunto de test (del 5-12%), demasiado débiles para tener valor predictivo real.

**Recomendación clara:** No merece la pena usar estos patrones para jugar a Euromillones. La equiprobabilidad sigue siendo la hipótesis más sólida.

---

## 📥 Datos

| Campo | Valor |
|---|---|
| Sorteos cargados | **1951** |
| Rango | 2004-02-13 → 2026-06-23 (22,4 años) |
| Fuente | [daowa89/lottery-archive](https://github.com/daowa89/lottery-archive) (GitHub, dataset público) |
| Formato | CSV `date,n1,n2,n3,n4,n5,s1,s2` (5 números 1-50 + 2 estrellas 1-12) |
| Almacenamiento | SQLite (`data/euromillones.db`) |

**Nota sobre el país:** Euromillones es transnacional (9 países comparten sorteo único). Los números sorteados son los mismos para todos los países. La fuente primaria (GitHub) **no incluye país sorteante** — por eso el "análisis por país" se reconvirtió a "análisis por períodos temporales" (cambios de reglas del juego en 2011, 2020 y 2022).

---

## 🧪 Fases del proyecto

| Fase | Descripción | Estado |
|---|---|---|
| **1** | Investigación de fuentes (Wikipedia, loteriasyapuestas.es, GitHub) | ✅ |
| **2** | Scraper + validador + SQLite + 23 tests | ✅ |
| **3** | Análisis descriptivo + 4 gráficos | ✅ |
| **4** | Análisis por períodos temporales (replanteo del análisis por país) | ✅ |
| **5** | Detector de patrones (frecuencia, correlaciones, rachas) | ✅ |
| **6** | Backtesting riguroso (Bonferroni, FDR, walk-forward) | ✅ |
| **7** | Informe final | ✅ |

---

## 📊 Hallazgos del análisis descriptivo (todos los datos)

### Distribución global
- **Suma media real:** 127.49 vs teórica 127.50 → coincide casi exacto ✅
- **Paridad más común:** 2 pares (679 sorteos, 34.8%)
- **Altos/bajos más común:** 2-3 números altos (66.4% de sorteos)
- **Consecutivos:** 65.2% de sorteos NO tienen números consecutivos (esperado por azar)

### Frecuencias (antes de corrección)

**Números con desviaciones notables:**
- 🔴 Número **22**: 153 apariciones (-21.6%), p=0.0026
- 🟡 Números 42, 44: +13.3%, p=0.064 (no significativo)

**Estrellas con desviaciones notables:**
- 🔴 **Estrella 12**: 174 apariciones (-46.5%), p<0.000001 ⭐⭐⭐
- 🔴 **Estrella 2**: 388 (+19.3%), p=0.0005
- 🔴 **Estrella 11**: 263 (-19.1%), p=0.0006
- 🔴 **Estrella 3**: 382 (+17.5%), p=0.0016

⚠️ **Advertencia:** Sin corrección por múltiples tests, ~5% de los 62 tests serían significativos por azar. Por eso necesitamos el backtesting.

---

## 🔬 Backtesting (split temporal 2021)

**Estrategia:**
- **Train:** 1379 sorteos (2004-02-13 → 2020-12-29)
- **Test:** 572 sorteos (2021-01-01 → 2026-06-23)

### Resultados

**Patrones significativos en train:** 9 (esperados por azar: 3.1)

**Supervivientes tras corrección:**
| Corrección | Sobreviven |
|---|---|
| **Bonferroni** (estricta) | 3 |
| **FDR Benjamini-Hochberg** (permisiva) | 6 |
| **Holm** (intermedia) | 3 |

### 🎯 Validación de supervivientes en test

| Estrella | Desviación Train | Desviación Test | p_test | ¿Sobrevive? |
|---|---|---|---|---|
| **2** | +23.6% | +9.1% | 0.375 | ✅ Confirmado |
| **3** | +19.7% | +12.2% | 0.232 | ✅ Confirmado |
| 8 | +20.5% | **-1.4%** | 0.891 | ❌ NO confirmado |
| 10 | -21.7% | **+1.7%** | 0.864 | ❌ NO confirmado |
| **11** | -24.7% | -5.6% | 0.585 | ✅ Confirmado |
| 12 | **-67.4%** | **+3.8%** | 0.707 | ❌ **NO confirmado** |

**🎯 Resultado clave:** El patrón más fuerte en train (estrella 12 con -67%) **no se confirma en absoluto en test**. Es regresión a la media: cuando un elemento se desvía mucho durante mucho tiempo, tiende a corregirse.

### Walk-forward validation (validación continua anual)

Para cada año del conjunto test, se identificaron los 5 números más fríos en el histórico anterior y se midió si seguían fríos ese año:

- **Tasa de acierto:** 60% (18 de 30 casos)
- **Esperado por azar:** ~50% (binomial, p>0.05)
- **Conclusión:** Las rachas negativas **no persisten más allá del azar**

---

## ⚠️ Advertencias técnicas (importantes)

1. **Equiprobabilidad sigue siendo la hipótesis nula.** Euromillones usa bombos físicos que se barajan antes de cada sorteo. Aunque se ha hablado de bolas "pesadas" en otras loterías, no hay evidencia documentada de sesgos mecánicos en Euromillones.

2. **El "análisis por país" no fue posible** porque el dataset de GitHub no incluye país. Euromillones es un sorteo único para los 9 países participantes, por lo que el resultado es el mismo para todos.

3. **El cambio de reglas en mayo 2011** amplió las estrellas de 9 a 12. Esto explica que en el período 2004-2011 las estrellas 10, 11 y 12 tuvieran 0 apariciones (no era porque no salieran, sino porque no existían). A partir de 2011, las 12 estrellas participan.

4. **El dataset de GitHub tiene 1951 sorteos** (en lugar de los ~4576 esperados para 22 años a 2 sorteos/semana). Posiblemente solo contiene 1 sorteo por semana o solo sorteos principales. Esto significa que **hay datos faltantes**, lo que reduce el poder estadístico.

5. **Las "desviaciones supervivientes" son débiles** (+9%, +12%, -5% en test). Comparado con el 50% de "mejora" que un apostante casual podría esperar sobre azar, **no hay base estadística para usarlos**.

---

## 📁 Entregables

### Estructura del proyecto
```
euromillones-analyzer/
├── README.md
├── INFORME_FINAL.md (este archivo)
├── requirements.txt
├── config.yaml
├── data/
│   ├── euromillones.db          # 1951 sorteos
│   └── raw/results.csv          # CSV original descargado
├── src/
│   ├── db/repository.py        # Repository SQLite
│   ├── db/schema.sql           # Schema
│   ├── downloader/scraper.py   # Pipeline de descarga
│   ├── downloader/sources.py   # Validador
│   ├── analysis/descriptive.py # Frecuencias, distribuciones
│   ├── analysis/patterns.py    # Detector de patrones
│   ├── analysis/backtest.py    # Backtesting
│   ├── analysis/statistics.py  # Bonferroni, FDR, Holm
│   ├── analysis/by_country.py  # Análisis por períodos
│   └── viz/heatmaps.py         # Visualizaciones
├── tests/
│   ├── test_validator.py       # 15 tests
│   └── test_repository.py      # 8 tests
├── reports/
│   ├── INFORME_FINAL.md
│   ├── backtest_resultados.json
│   └── graficos/
│       ├── 01_heatmap_numeros.png
│       ├── 02_heatmap_estrellas.png
│       ├── 03_desviaciones.png
│       └── 04_distribuciones.png
└── docs/
    └── fuentes_datos.md        # Investigación de fuentes
```

### Tests
- **23/23 tests pasan** (15 del validador + 8 del repository/integración)
- Tiempo de ejecución: 56s

---

## 💡 Recomendaciones finales

1. **No usar este análisis para jugar a Euromillones.** Las desviaciones supervivientes (+9% en estrella 2, +12% en estrella 3) son estadísticamente marginales y económicamente irrelevantes.

2. **¿Por qué la estrella 12 se desvió tanto en train?** Probablemente por regresión a la media + efecto de su introducción tardía (mayo 2011). El bombo de las estrellas es físicamente igual al de las otras 11.

3. **Si quieres seguir investigando:**
   - Buscar datasets con más sorteos (¿quizás hay otra fuente que cubra los 4576 esperados?)
   - Probar con Euromillones HotPicks (sorteos especiales del Reino Unido con datos por país)
   - Analizar **El Millón** (juego asociado español con mecánica diferente)

4. **Lo que sí es interesante para la educación:** El método es correcto. La regresión a la media y los falsos positivos por múltiples tests son trampas reales del análisis de datos. Este proyecto sirve como ejemplo de cómo NO caer en ellas.

---

## 📈 Comandos útiles

```bash
# Recargar datos (si hay nuevos sorteos)
PYTHONPATH=. python3 -c "
from src.db.repository import SorteoRepository
from src.downloader.scraper import pipeline_descarga
pipeline_descarga(SorteoRepository('data/euromillones.db'))
"

# Tests
source venv/bin/activate
pytest tests/ -v

# Backtesting
PYTHONPATH=. python3 run_phase6.py

# Análisis descriptivo
PYTHONPATH=. python3 run_phase3.py
```

---

**Conclusión final:** Euromillones se comporta como un sorteo genuinamente aleatorio. Las desviaciones aparentes son ruido estadístico corregido por el backtesting. Jugar con estos "patrones" no mejora las probabilidades sobre azar.
