# Informe 05 — Entropía e información mutua

**Fecha:** 2026-06-25  
**Carpeta:** `euromillones-analyzer/`  
**Archivo fuente:** `run_approach_05_entropy_mi.py`  
**Datos:** `reports/informes/informe_05_entropia_info_mutua.json`

---

## 🎯 Objetivo

Medir la **información compartida** entre variables del sorteo. Si hay dependencias estadísticas, la información mutua I(A;B) será positiva. Bajo independencia, I(A;B) = 0.

---

## 📐 Metodología

1. **Información mutua entre pares de números** (top 15 más frecuentes):
   - I(A;B) = H(A) + H(B) - H(A,B)
   - Mide cuántos bits de información da saber A sobre B
   - **Independiente**: I ≈ 0
   - **Dependiente**: I > 0

2. **Información mutua entre sumas consecutivas** I(suma_t, suma_{t+1}):
   - Categorización en 10 bins
   - Chi² de contingencia → conversión a MI

3. **Entropía por día de semana**: martes vs viernes.

4. **Entropía del sistema completo**:
   - Combinaciones posibles = C(50,5) × C(12,2) = 139,838,160
   - H_max = log₂(139.8M) ≈ 27.06 bits

---

## 📊 Resultados

### Top 10 pares de números con mayor información mutua

| num_a | num_b | p_a | p_b | p_ab | H(A) bits | H(B) bits | **MI bits** |
|---|---|---|---|---|---|---|---|
| 44 | 42 | 0.113 | 0.113 | 0.0056 | 0.510 | 0.510 | **0.00446** |
| 21 | 37 | 0.108 | 0.107 | 0.0056 | 0.494 | 0.490 | 0.00322 |
| 19 | 17 | 0.111 | 0.110 | 0.0062 | 0.504 | 0.499 | 0.00321 |
| 44 | 45 | 0.113 | 0.105 | 0.0062 | 0.510 | 0.485 | 0.00295 |
| 17 | 37 | 0.110 | 0.107 | 0.0062 | 0.499 | 0.490 | 0.00277 |
| 21 | 25 | 0.108 | 0.105 | 0.0062 | 0.494 | 0.483 | 0.00246 |
| 42 | 25 | 0.113 | 0.105 | 0.0067 | 0.510 | 0.483 | 0.00236 |
| 42 | 21 | 0.113 | 0.108 | 0.0072 | 0.510 | 0.494 | 0.00218 |
| 35 | 27 | 0.105 | 0.104 | 0.0062 | 0.485 | 0.482 | 0.00216 |
| 10 | 25 | 0.109 | 0.105 | 0.0067 | 0.496 | 0.483 | 0.00200 |

**MI media: 0.0007 bits** (esperado ~0 bajo independencia).

**MI máxima: 0.00446 bits** (0.45% de un bit). Prácticamente cero.

### Información mutua entre sumas consecutivas

| Métrica | Valor |
|---|---|
| MI(suma_t, suma_{t+1}) | **0.0282 bits** |
| Esperado bajo independencia | ~0 bits |
| Número de transiciones | 1950 |

La MI de 0.028 bits es **muy baja**. Significa que saber la suma del sorteo anterior **apenas reduce la incertidumbre** sobre la del siguiente.

### Entropía por día de semana

| Día | n | H bits | Suma media |
|---|---|---|---|
| Martes | 787 | **5.6362** | 127.34 |
| Viernes | 1159 | **5.6384** | 127.60 |

**Las entropías son prácticamente idénticas** entre martes y viernes (difieren en 0.0022 bits, < 0.05%). No hay diferencia en la "informatividad" del sorteo según el día.

### Entropía del sistema completo

| Métrica | Valor |
|---|---|
| Combinaciones posibles (5 de 50 + 2 de 12) | **139,838,160** |
| Entropía máxima | **27.06 bits** ≈ 3.38 bytes |
| Sorteos observados | 1951 |
| Cobertura del espacio de estados | **0.0014%** |

---

## 🎓 Conclusiones

1. **Información mutua prácticamente cero entre números** (media 0.0007 bits). Los pares top (44-42 con MI=0.00446 bits) son **ruido estadístico** — la MI es 100x más pequeña que un solo bit.

2. **La información del sorteo anterior no ayuda a predecir el siguiente** (MI = 0.028 bits).

3. **Martes y viernes son equivalentes** en entropía y suma media. No hay diferencia operativa.

4. **Hemos cubierto el 0.0014% del espacio de estados** en 22 años. Eso es 1 de cada 71,700 combinaciones posibles. **No es de extrañar que veamos desviaciones** — con 1951 sorteos en 140M combinaciones, hay muchos "huecos" en el espacio de resultados.

---

## ⚠️ Advertencias

- MI = 0.028 bits NO es cero. Pero es del orden de lo esperado por azar en una serie tan corta.
- El espacio de combinaciones (140M) es enorme — los 1951 sorteos son una **muestra ínfima**. Esto explica por qué vemos desviaciones en frecuencias.
- La "cobertura" del 0.0014% es engañosa: no significa que estamos viendo "lo mismo" muchas veces, significa que **hemos tocado muy poco del espacio**.

---

## 📁 Entregables

- Script: `run_approach_05_entropy_mi.py`
- JSON con resultados detallados: `informe_05_entropia_info_mutua.json`
