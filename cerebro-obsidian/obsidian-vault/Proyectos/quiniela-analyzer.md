# quiniela-analyzer

## Descripción
Análisis predictivo de La Quiniela (Quiniela/14) usando ML.

## Estado
🚧 **v3 en progreso** — Plan en `~/.hermes/plans/2026-08-04_quiniela-info-v3.md`

## Stack
- Python 3.11
- scikit-learn, pandas, numpy
- lightgbm (v3, nuevo)
- SQLite
- httpx + beautifulsoup4

## Histórico de versiones

### v2 (actual, julio 2026)
- 68 features: ELO + Transfermarkt (squad, age, foreigners, market value) + stadium + name embeddings + news
- Modelos: LogReg, Poisson, Dixon-Coles, Odds-implied, Ensemble
- **LogReg val accuracy: 46.22%** vs baseline always_H = 46.88% (−0.66pp) ❌
- Apuesta selectiva (≥45%) sí bate baseline (+5.5pp) pero en submuestra pequeña
- Reporte: `data/reports/rich_backtest_v2_2026-07-31.html`

### v3 (en progreso, agosto 2026)
- Plan: `~/.hermes/plans/2026-08-04_quiniela-info-v3.md`
- 4 fuentes nuevas: cuotas Bet365, forma reciente, H2H, fatiga calendario
- Modelo target: LightGBM v3 + ensemble v3
- Target: val accuracy ≥+2pp sobre baseline en cobertura total

## Ubicación
`/home/vhdez/desarrollos-hermes/quiniela-analyzer/`

## Tags
#proyecto #ml #quiniela
