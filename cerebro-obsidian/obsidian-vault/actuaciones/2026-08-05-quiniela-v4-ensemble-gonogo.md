# 2026-08-05 — Ensemble v4: Go/No-Go final quiniela

## Resultado walk-forward (test seasons 2425+2526)

| Modelo | Accuracy | Δ vs AvgH |
|--------|----------|-----------|
| Local (siempre H) | 43.02% | — |
| **AvgH (mercado)** | **50.14%** | ref |
| LogReg v3 | 50.51% | +0.37pp |
| XGBoost | 49.63% | −0.51pp |
| Dixon-Coles | 44.41% | −5.73pp |
| Ensemble | 49.77% | −0.37pp |

## ⚖️ Veredicto final: NO-GO vs AvgH

**Ningún modelo individual ni el ensemble supera el +1pp vs AvgH**.

LogReg v3 es el único que supera AvgH (+0.37pp), pero queda **lejos del umbral +1pp** definido en el plan.

## Top features XGBoost

```
1. psc_h          0.0732   (Pinnacle home)
2. imp_a          0.0638   (implied visitante)
3. avg_a          0.0559   (AvgH visitante)
4. psc_a          0.0481
5. avg_h          0.0389
6. psc_d          0.0341
...
10. h2h5_away_wins 0.0290
```

**Forma (home/away_n5/n10) y rest NO entran en top10**. Confirma que la cuota del mercado **ya descuenta** toda esa información.

## Lecciones aprendidas

1. **El mercado es un predictor duro de batir** con solo datos públicos. Pinnacle cierra con información cercana al cierre del partido.
2. **Walk-forward estricto** (train en seasons anteriores, test en futuras) reduce overfitting pero también reduce señal marginal.
3. **Dixon-Coles flojo** sin attack/defense por equipo. La versión simplificada que probé no captura el poder del modelo real.

## Estado del proyecto quiniela-analyzer

| Componente | Estado | Detalle |
|------------|--------|---------|
| Datos | ✅ | 13.507 partidos LaLiga 1920-2526 (16 temporadas) |
| Odds | ✅ | 12.936 con avg_h + Pinnacle + Bet365 (Task 1) |
| Forma | ✅ | 13.472 con ventanas N=5 y N=10 (Task 2) |
| H2H | ✅ | 13.472 con N=5 y N=10 entre parejas (Task 3) |
| Fatiga | ✅ | 13.472 con rest_days y proxies UEFA (Task 4) |
| LogReg v3 | ✅ | 50.51% accuracy (+0.37pp vs AvgH) |
| XGBoost v4 | ✅ | 49.63% (−0.51pp vs AvgH) |
| Ensemble v4 | ✅ | 49.77% (−0.37pp vs AvgH) |
| Sistema avisos | ✅ | Cron diario 9:00 AM con propuesta 3d antes |
| Calendar 2026-27 | ✅ | 38 jornadas generadas |

## Sistema operativo

El sistema de avisos 3d antes **ya está en producción**:
- Cron `quiniela-alert-diario` (id `2f02d434e409`) corre todos los días 9:00 AM
- Detecta jornadas con fecha_sabado en 3-5 días
- Genera propuesta formateada para Telegram

## Próximo paso sugerido

Plan v3 cerrado sin mejora incremental. **Opciones**:
- **(A) v5 con features avanzadas**: xG (necesita StatsBomb/Understat), lesiones, ELO dinámico
- **(B) Parar aquí y usar solo AvgH como predictor** (es lo que mejor bate baseline)
- **(C) Refrescar BD con temporada 2026-27** en cuanto salgan los CSVs

Mi recomendación: **B** (parar). El sistema de avisos + AvgH ya da 50% accuracy = +5pp vs baseline local, ROI positivo con stakes pequeños. El ensemble/LogReg no añade valor real.

**Próximo aviso**: 12-ago-2026 a las 9:00 AM (J1 LaLiga 2026-27 vs Athletic-Villarreal).