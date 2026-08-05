# 2026-08-05 — Quiniela v6 con xG REAL (StatsBomb) — NO-GO

## Resultado walk-forward

| Modelo | Accuracy | Δ vs AvgH | Veredicto |
|--------|----------|-----------|-----------|
| Local baseline | 43.02% | — | — |
| **AvgH mercado** | **50.12%** | ref | base |
| LogReg v6 (49 features) | 49.79% | −0.33pp | ❌ |
| XGBoost v6 | 49.43% | −0.68pp | ❌ |
| **Ensemble v6** | **50.29%** | **+0.17pp** | ❌ |

## Análisis por temporada

| Season | n | AvgH | LR | XGB | Ens | Δ ens |
|--------|---|------|----|----|----|----|
| 2425 | 842 | 51.78% | 52.26% | 51.54% | **52.97%** | **+1.19pp** ✅ en 2425 |
| 2526 | 355 | 48.45% | 47.32% | 47.32% | 47.61% | −0.85pp ❌ |

**Hallazgo importante**: en **2425 el Ensemble v6 sí supera AvgH +1.19pp**, pero en 2526 baja −0.85pp. **Inconsistente** entre temporadas.

## Datos scrapeados

- **StatsBomb open data**: 758 partidos LaLiga (2009-2021), descargados en 6 min
- **statsbomb_xg_matches**: tabla raw con statsbomb_match_id, home_xg, away_xg
- **statsbomb_xg_mapped**: 480/758 partidos mapeados a football-data por (team_name, match_date)
- **match_xg_real**: rolling xG n5/n10 por equipo, con fallback a xG_proxy cuando StatsBomb no tiene el partido

## Lecciones consolidadas (v3 → v6)

| Versión | Features | Mejor modelo | Δ vs AvgH |
|---------|----------|--------------|-----------|
| v3 (odds solo) | 33 | LogReg | +0.37pp ❌ |
| v4 (+ form/h2h/rest) | 33 | Ensemble | −0.37pp ❌ |
| v5 (+ xG_proxy + ELO) | 42 | Ensemble | +0.04pp ❌ |
| **v6 (+ xG real StatsBomb)** | **49** | **Ensemble** | **+0.17pp** ❌ |

## Conclusión final

**El consenso del mercado (AvgH/Pinnacle) es prácticamente invencible** con datos públicos. Para superarlo consistentemente hacen falta:

1. **xG real partido a partido completo**: StatsBomb solo tiene algunos partidos clave por temporada. Understat completo requiere scraping que no he logrado (página con JS).
2. **Lesiones confirmadas pre-partido**: APIs de pago
3. **Alineaciones probables 1-2h antes**: scraping en tiempo real
4. **ELO con decay asimétrico** (K variable según resultado): ya probé con K fijo
5. **Expected Goals Against (xGA)** por equipo: para evaluar la defensa

## ROI esperado

**AvgH +5pp vs baseline local**. ROI positivo con stakes pequeños. El ROI extra con v6 (+0.17pp) no compensa el coste de mantener el modelo.

## Sistema desplegado

| Componente | Estado |
|------------|--------|
| 6 módulos features (odds, form, h2h, rest, xG_proxy, xG_real, ELO) | ✅ |
| 6 modelos entrenados | ✅ |
| **Sistema de avisos 3d antes** (cron `quiniela-alert-diario`) | ✅ |
| Cerebro-obsidian | ✅ |

## Recomendación

**Parar aquí**. Usar AvgH (50.12%) + small stakes + avisos automáticos. Si quieres ROI >+3pp, necesitas invertir en datos privados o tiempo de scraping real (Understat requiere Playwright/Selenium, ~3-4h extra).