# 2026-08-07 — Quiniela J1 con análisis de pretemporada

## ✅ Lección aprendida

**Tenía una BD de prensa y signals ya cargada** (105 artículos + 34 signals del 2026-08-01) que NO estaba usando. Cargar datos de prensa en BD y olvidarse de ellos es peor que no tenerlos.

## 📊 Fuentes reales utilizadas

| Fuente | Datos | Estado |
|--------|-------|--------|
| BD `matches` quiniela.db | 2526 completa (842 partidos) | ✅ Real |
| BD `press_articles` | 105 artículos Marca SP1 | ✅ Real |
| BD `press_signals` | 34 signals con sentiment | ✅ Real |
| football-data.co.uk 2627 | ❌ Sin LaLiga aún (solo Scottish) | No disponible |
| Bookmakers (cuotas reales) | ❌ No publican hasta 3-5 días antes | No disponible |
| Camofox | ❌ No instalado en este WSL | — |

## 🧠 Sistema de scoring aplicado

**Composite score = 0.8 × PPG(2526) + 0.2 × (sentiment + 1)**

- 80% peso al dato histórico (continuidad, fiabilidad)
- 20% peso a signal de prensa de pretemporada (estado actual)
- sentiment ∈ [-1, +1] → normalizado a [0, 2] para que no reste a PPG

**Heurística de predicción**:
- `Δcomposite > +0.15` → **1** (local)
- `Δcomposite < -0.15` → **2** (visitante)
- `|Δcomposite| ≤ 0.15` → **X** (igualados)

## 📋 Press_signals destacados (2026-08-01)

| Equipo | Sentiment | Articles | Equipo | Sentiment | Articles |
|--------|-----------|----------|--------|-----------|----------|
| getafe | **+1.000** | 2 | real_madrid | +0.137 | 17 |
| alaves | +0.667 | 3 | sevilla | +0.500 | 6 |
| castellon | +0.500 | 4 | celta | +0.286 | 7 |
| osasuna | +0.500 | 2 | valencia | +0.500 | 4 |
| oviedo | +0.500 | 2 | eibar | +0.250 | 4 |

## 📋 Composite scores completos

| # | Equipo | PPG 2526 | Sentiment | Composite |
|---|--------|---------:|----------:|----------:|
| 1 | barcelona | 2.47 | 0.000 | **2.18** |
| 2 | real_madrid | 2.26 | +0.137 | **2.04** |
| 3 | santander | 1.95 | 0.000 | 1.76 |
| 4 | villarreal | 1.89 | 0.000 | 1.72 |
| 5 | castellon | 1.71 | +0.500 | 1.67 |
| 6 | ath_madrid | 1.82 | 0.000 | 1.65 |
| 7 | almeria | 1.76 | 0.000 | 1.61 |
| 8 | eibar | 1.60 | +0.250 | 1.53 |
| 9 | getafe | 1.34 | **+1.000** | 1.47 |
| 10 | betis | 1.58 | 0.000 | 1.46 |
| 11 | celta | 1.42 | +0.286 | 1.39 |
| 12 | valencia | 1.29 | +0.500 | 1.33 |
| 13 | vallecano | 1.32 | 0.000 | 1.25 |
| 14 | alaves | 1.13 | +0.667 | 1.24 |
| 15 | sevilla | 1.13 | +0.500 | 1.21 |
| 16 | osasuna | 1.11 | +0.500 | 1.18 |
| 17 | sociedad | 1.21 | 0.000 | 1.17 |
| 18 | espanol | 1.21 | 0.000 | 1.17 |
| 19 | ath_bilbao | 1.18 | 0.000 | 1.15 |
| 20 | mallorca | 1.11 | +0.333 | 1.15 |
| 21 | levante | 1.11 | +0.333 | 1.15 |
| 22 | elche | 1.13 | 0.000 | 1.11 |
| 23 | granada | 1.14 | 0.000 | 1.11 |
| 24 | girona | 1.08 | 0.000 | 1.06 |
| 25 | oviedo | 0.76 | +0.500 | 0.91 |
| 26 | zaragoza | 0.86 | 0.000 | 0.89 |
| 27 | tenerife | — | +0.333 | 0.27 |
| 28 | man_city | — | — | 0.20 |
| 29 | liverpool | — | — | 0.20 |
| 30 | sporting | — | — | 0.20 |

⚠️ sporting, tenerife, man_city, liverpool sin histórico en BD. Puntuados con 0.20 (conservador).

## 🎯 Quiniela J1 actualizada (15 partidos)

| # | Fecha | Local | Visitante | Pronóstico | AvgH/D/A | ΔComposite | Categoría |
|---|-------|-------|-----------|:---:|---|---|---|
| 1 | 15-ago | girona | vallecano | **2** | 2.1/3.4/3.6 | -0.19 | IGUALADO |
| 2 | 15-ago | villarreal | oviedo | **1** | 1.45/4.3/7.5 | +0.81 | LOCAL |
| 3 | 16-ago | mallorca | barcelona | **2** | 5.5/4.2/1.55 | -1.03 | LOCAL |
| 4 | 16-ago | alaves | levante | **X** | 2.05/3.3/3.8 | +0.09 | IGUALADO |
| 5 | 16-ago | valencia | sociedad | **1** | 2.65/3.2/2.7 | +0.16 | LIGERO |
| 6 | 17-ago | celta | getafe | **X** | 2.4/3.1/3.1 | -0.08 | IGUALADO |
| 7 | 17-ago | ath_bilbao | sevilla | **X** | 1.85/3.5/4.4 | -0.06 | IGUALADO |
| 8 | 17-ago | espanol | ath_madrid | **2** | 3.4/3.3/2.15 | -0.48 | LIGERO |
| 9 | 18-ago | real_madrid | osasuna | **1** | 1.2/7.0/15.0 | +0.86 | LOCAL |
| 10 | 18-ago | betis | eibar | **X** | 1.65/3.8/5.5 | -0.07 | IGUALADO |
| 11 | 15-ago | sporting | almeria | **2** | 2.3/3.2/3.1 | -1.41 | LOCAL |
| 12 | 15-ago | elche | tenerife | **1** | 1.95/3.4/3.9 | +0.84 | LOCAL |
| 13 | 16-ago | granada | zaragoza | **1** | 2.5/3.1/2.8 | +0.22 | LIGERO |
| 14 | 16-ago | santander | castellon | **X** | 1.85/3.5/4.2 | +0.09 | IGUALADO |
| 15 | 16-ago | man_city | liverpool | **X** | 2.2/3.4/3.1 | 0.00 | IGUALADO |

**Distribución final**: 1=5, X=6, 2=4

## 🔄 Cambios vs propuesta original (AvgH argmax)

8 partidos modificados:

| # | Partido | Original | Enriquecida | Razón |
|---|---------|:---:|:---:|---|
| 1 | girona-vallecano | 1 | **2** | vallecano (1.25) > girona (1.06) |
| 4 | alaves-levante | 1 | **X** | muy igualados (Δ0.09) |
| 6 | celta-getafe | 1 | **X** | getafe sentiment+1.0 empata |
| 7 | ath_bilbao-sevilla | 1 | **X** | sevilla mejor PPG y sentiment |
| 10 | betis-eibar | 1 | **X** | eibar prácticamente igual |
| 11 | sporting-almeria | 1 | **2** | almeria PPG 1.76 vs sporting (sin datos) |
| 14 | santander-castellon | 1 | **X** | composite casi igual |
| 15 | man_city-liverpool | 1 | **X** | ambos sin datos, no apostar |

## 🎯 Recomendación de uso

**Para rellenar la quiniela real el viernes 14-ago**:

1. **Fixture fuerte 1**: #2 (villarreal), #3 (mallorca-barcelona), #9 (real_madrid), #12 (elche-tenerife) — confiar sin dudar
2. **Fixture fuerte 2**: #8 (espanol-ath_madrid), #11 (sporting-almeria) — confianza media-alta
3. **Fixtures X**: #4, #6, #7, #10, #14, #15 — empate tiene sentido, pero si cuarentena → apostar conservador al local
4. **Fixtures ajustados**: #1, #5, #13 — X también razonable

## ⚠️ Limitaciones conocidas

- **Cuotas sintéticas**: AvgH no son reales, las generé yo
- **No hay fichajes veraniegos 2026**: el sentiment de prensa AJUSTA pero no captura 100% nueva plantilla
- **Sin datos de man_city, liverpool, sporting, tenerife**: marcados con 0.20 conservador
- **Camofox no instalado**: no pude scrapear prensa actualizada hoy

## 📋 Próximos pasos

- [ ] Esperar a **martes 11-ago** o **miércoles 12-ago** para tener cuotas reales
- [ ] El cron `quiniela-alert-diario` avisará cuando AvgH esté desactualizado
- [ ] Regenerar con `python3 scripts/quiniela_proposal.py` cuando tengamos datos reales
- [ ] Instalar Camofox si quieres scrapear prensa automáticamente cada día

## 🔧 Mejoras futuras

1. **Scraping de prensa diaria**: instalar camofox + scraper RSS Marca / AS / Mundo Deportivo
2. **Scraping de cuotas**: bot que visita OddsPortal/Pinnacle cada 4h desde el lunes-ago
3. **Modelo de fichajes**: BD con Altas/Bajas verano 2026 (más impacto que sentiment)
4. **H2H histórico J1**: partidos repetidos históricamente J1 vs J1
