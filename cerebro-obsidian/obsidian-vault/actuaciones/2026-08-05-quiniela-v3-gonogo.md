# 2026-08-05 — quiniela v3: Go/No-Go LogReg

## Resultado

| Modelo | Accuracy promedio (2425+2526, walk-forward) | Δ vs AvgH | Δ vs Local |
|--------|------|------|------|
| Local (siempre H) | 43.02% | — | — |
| AvgH argmax (mercado) | **50.14%** | — | +7.12pp |
| **LogReg v3** (odds + form + h2h + rest) | **50.51%** | **+0.37pp** | **+7.49pp** |

## ⚠️ Veredicto: NO-GO sobre +1pp vs AvgH

- ✅ GO claro vs baseline local (+7.49pp)
- ❌ NO-GO vs consenso mercado (+0.37pp, falta +0.63pp para +1pp)

## ¿Por qué no supera AvgH?

1. **Cuotas ya incorporan toda la info pública**. AvgH refleja consenso de 30+ bookmakers e incluye forma, h2h, lesiones, fatiga Champions — difícil ganarle con datos que también son públicos.
2. **LogReg es lineal**. No captura interacciones (p.ej. "local descansado + visitante en racha visitante" es super-aditivo).
3. **Walk-forward estricto** reduce overfitting pero también quita margen.

## Top features (LogReg v3)

1. `avg_h` / `avg_d` / `imp_a` (odds) — pesos dominantes
2. `away_n5_l` (forma visitante reciente) — tiene peso real
3. `psc_h` / `psc_d` (Pinnacle sharp) — confirma señal del mercado
4. `home_n5_w` — forma local

Forma, h2h y rest tienen pesos menores pero no despreciables. **El modelo iguala el mercado pero no lo supera**.

## Tabla resumen plan v3

| Task | Tabla | Filas | Señal |
|------|-------|-------|-------|
| 1 — Cuotas | match_odds | 12.936 | +5pp vs baseline |
| 2 — Forma | match_form | 13.472 | correlación +0.20 |
| 3 — H2H | match_h2h | 13.472 | derbis accuracy distinta |
| 4 — Rest | match_rest | 13.472 | visitante 4d +4.5pp |
| **5 — LogReg v3** | training_set_v3 | **5.768** | **+0.37pp vs AvgH** |

## Siguiente paso

Plan v3 cerrado pero sin mejora incremental. **Opciones para v4**:

- **(A) Ensemble LogReg + XGBoost + Dixon-Coles Poisson** → vota ponderado
- **(B) Features de venue_bias** (intuición campos malditos visitante)
- **(C) Refrescar BD con temporada 2026-27** (en cuanto salgan CSVs)

Estado del proyecto: **sistema de avisos 3d antes funcional**, J1 (15-ago-2026) genera propuesta vacía porque no hay cuotas aún. **Próximo aviso**: 12-ago-2026 a las 9:00 AM.