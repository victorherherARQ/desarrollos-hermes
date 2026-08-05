# 2026-08-05 — Quiniela v5 con xG_proxy + ELO dinámico — NO-GO post-fix

## Resultado walk-forward (2425+2526, anti-leakage aplicado)

| Modelo | Accuracy | Δ vs AvgH | Veredicto |
|--------|----------|-----------|-----------|
| Local baseline | 43.02% | — | — |
| **AvgH mercado** | **50.14%** | ref | base |
| LogReg v5 (42 features) | 50.00% | **−0.14pp** | ❌ NO-GO |
| XGBoost v5 | 48.66% | −1.48pp | ❌ |
| Ensemble v5 | 50.18% | +0.04pp | ❌ NO-GO |

## Hallazgo crítico: LEAKAGE detectado y corregido

El primer resultado dio **+10pp vs AvgH** (LogReg 60.96%, Ensemble 59.80%). Sospeché que era demasiado bueno para ser real.

**Debug**: en `seed_match_elo.py`, el rating POST-partido se guardaba con `match_date = matchday_date`. Al usar `merge_asof(direction="backward")` para un partido N, el merge_asof encontraba el rating POST del propio partido N, **no el anterior estricto**. Esto es leakage temporal.

**Solución**: shift +1 día en los ratings → POST del día X queda como "PRE del día X+1". Así el merge_asof salta correctamente.

Tras aplicar el fix, **el modelo NO supera AvgH**.

## Lección

El consenso del mercado (AvgH/Pinnacle) ya descuenta el ~100% de la información pública disponible:
- Forma reciente (goles, resultados últimos 5-10 partidos)
- Head-to-head histórico
- Fatiga por calendario (UEFA Champions/Europa afecta a equipos top)
- Diferencias de plantilla entre temporadas
- ELO dinámico

Para **superar** AvgH hacen falta datos que el mercado **no descuenta totalmente**:
- **xG real con shot locations** (StatsBomb, Understat scraping)
- **Lesiones confirmadas pre-partido** (APIs privadas tipo Football-Injury-API)
- **Alineaciones probables** (1-2h antes del pitido inicial)
- **ELO dinámico con decay asimétrico** (más peso a partidos recientes)

## Estado de tablas v5

| Tabla | Filas | Cobertura | Notas |
|-------|-------|-----------|-------|
| match_xg_proxy | 12.936 | 99.7% | n5, n10, diff |
| match_elo | 13.472 | 99.7% | pre-partido anti-leakage |
| elo_ratings | 26.944 | — | 13.472 partidos × 2 equipos |

## Decisión

**Plan v3-v5 cerrado**. El sistema de quiniela queda con:
- AvgH como predictor principal (50.14% accuracy, +7pp vs local)
- Sistema de avisos 3 días antes (cron `quiniela-alert-diario`)
- Calendar 2026-27 generado (38 jornadas)

**Siguiente paso realista** (no recomendado): v6 con xG real via scraping Understat ~3-4h extra de trabajo, ROI esperado +0.5-1.0pp vs AvgH.

**Recomendación**: usar AvgH como predictor. Invertir tiempo en features privadas si quieres ROI real.

## Commits relevantes

- `e68b6d8` h2h (Task 3)
- `77e8b58` fatiga (Task 4)
- `f98820b` LogReg v3 (Task 5)
- `81b5421` ensemble v4 (Task 6)
- (siguiente) ensemble v5 con xG+ELO (Task 7)

## Próximo aviso programado

**12-ago-2026 a las 9:00 AM** → propuesta J1 LaLiga 2026-27 (Athletic-Villarreal u otros 14 partidos según sorteo).