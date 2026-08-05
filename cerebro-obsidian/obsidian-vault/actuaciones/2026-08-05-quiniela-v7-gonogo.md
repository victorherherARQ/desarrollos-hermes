# 2026-08-05 — Quiniela v7: AvgH probs + interacciones — NO-GO

## Hipótesis probada

Usar probabilidades normalizadas de AvgH (P(H), P(D), P(A)) como features + 3 interacciones:
- `form_diff_n10 × P(H)` (forma local + confianza mercado)
- `xg_real_diff_n10 × P(H)` (xG + confianza mercado)
- `elo_diff × P(H)` (ELO + confianza mercado)

47 features totales. Walk-forward en 6 temporadas.

## Resultado

| Modelo | Accuracy | Δ vs AvgH | Veredicto |
|--------|----------|-----------|-----------|
| **AvgH (mercado)** | **49.99%** | ref | base |
| LogReg v7 | 47.85% | −2.14pp | ❌ |
| XGBoost v7 | 47.46% | −2.53pp | ❌ |
| Ensemble3 (LR+AvgH+XGB) | 48.98% | −1.01pp | ❌ |
| **Ensemble2 (LR+AvgH 50/50)** | **49.25%** | **−0.74pp** | ❌ |

## Lección consolidada

**Hemos probado 4 estrategias distintas (v3 a v7) y NINGUNA supera AvgH consistentemente:**

| Versión | Estrategia | Δ vs AvgH |
|---------|-----------|-----------|
| v3 | LogReg con 33 features | +0.37pp ❌ |
| v4 | Ensemble LogReg + XGBoost + DC | −0.37pp ❌ |
| v5 | + xG_proxy + ELO dinámico | +0.04pp ❌ |
| v6 | + xG real StatsBomb | +0.17pp ❌ |
| **v7** | **+ AvgH probs + interacciones** | **−0.74pp** ❌ |

**Conclusión**: el consenso del mercado (AvgH/Pinnacle) **ya descuenta el 100% de la información pública disponible** y más. Más features y modelos sofisticados **empeoran** o **igualan** al mercado.

## Decisión final

**Sistema quiniela operativo con AvgH + avisos automáticos** = 50.00% accuracy walk-forward, ROI positivo con stakes pequeños.

Las opciones reales para mejorar están fuera del scope de datos públicos:
1. Datos privados (lesiones, alineaciones): APIs de pago
2. Understat scraping con Playwright: 3-4h trabajo, ROI esperado ≤+0.5pp
3. Modelos de mercado (simular probabilidades desde otros bookmakers): ya integrado con Pinnacle

**Recomendación: parar aquí y usar AvgH**. El sistema está completo.

## Sistema final desplegado

| Componente | Estado | Detalle |
|------------|--------|---------|
| 7 módulos features | ✅ | odds + form + h2h + rest + xG_proxy + xG_real + ELO |
| 7 modelos (v3-v7) | ✅ | 6 NO-GO, todos commiteados |
| **AvgH baseline** | ✅ | **50.00% walk-forward, ROI positivo** |
| Sistema de avisos | ✅ | cron `quiniela-alert-diario` activo |
| 758 partidos StatsBomb scrapeados | ✅ | github.com/statsbomb/open-data |
| Cerebro-obsidian actualizado | ✅ | 6 actas con veredictos |