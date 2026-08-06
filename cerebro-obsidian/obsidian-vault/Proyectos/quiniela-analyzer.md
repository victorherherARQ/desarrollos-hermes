---
estado: bloqueado
fecha_inicio: 2025-06-01
personas: [Victor]
tags: [proyecto/bloqueado, area/trabajo]
---

# quiniela-analyzer

## Descripción
Análisis predictivo de La Quiniela (Quiniela/14) usando ML.

## Estado
🚧 **v7 cerrado** — AvgH confirmado como techo (50.12% baseline). v3-v7 todos NO-GO.

## Stack
- Python 3.11
- scikit-learn, pandas, numpy
- lightgbm, xgboost
- SQLite
- httpx + beautifulsoup4

## Histórico de versiones

### v2 (julio 2026)
- 68 features: ELO + Transfermarkt (squad, age, foreigners, market value) + stadium + name embeddings + news
- Modelos: LogReg, Poisson, Dixon-Coles, Odds-implied, Ensemble
- **LogReg val accuracy: 46.22%** vs baseline always_H = 46.88% (−0.66pp) ❌
- Apuesta selectiva (≥45%) sí bate baseline (+5.5pp) pero en submuestra pequeña

### v3-v7 (agosto 2026)
- Plan: `~/.hermes/plans/2026-08-04_quiniela-info-v3.md`
- Features: cuotas Bet365/Pinnacle + forma reciente + H2H + fatiga calendario + xG_statsbomb + ELO
- Modelos: LogReg + XGBoost + Dixon-Coles + Ensemble (49 features)
- Walk-forward 6 seasons: todos NO-GO vs AvgH
- **AvgH (50.12%) confirmado como techo con datos públicos**
- Sistema de avisos 3d antes funcionando (cron activo)

## Ubicación
`/home/vhdez/desarrollos-hermes/quiniela-analyzer/`

## Decisión
Plan quiniela v3-v7 **cerrado**. No proseguir sin orden explícita. Sistema de avisos queda operativo.

## Tareas asociadas

```dataview
LIST
FROM "Tareas"
WHERE contains(proyecto, "quiniela-analyzer")
```
