# Quiniela Analyzer

Análisis predictivo de La Quiniela (España) y Quinigol usando datos
históricos de fútbol de football-data.co.uk.

## Datos

* **Partidos históricos**: LaLiga 1ª (SP1) y 2ª división (SP2) desde 1993-94
  hasta la temporada actual. Formato CSV descargado de football-data.co.uk.
* **Quiniela**: 15 partidos por jornada con signo 1/X/2 + Pleno al 15 (M/0/1/2/M0/01/...).
* **Quinigol**: 6 partidos con resultado exacto (0-0, 0-1, ..., M-M).

## Acercamientos aplicados

1. **ELO ratings** — fuerza dinámica de cada equipo con factor local/visitante
2. **Poisson bivariante** — modela goles local/visitante como variables Poisson independientes
3. **Dixon-Coles** — extensión de Poisson que corrige el sesgo en marcadores bajos (0-0, 1-0, 0-1, 1-1)
4. **Ensemble** — promedio ponderado de los tres basado en backtesting

## Estructura

```
├── data/             # CSV crudo + SQLite cache
├── src/
│   ├── db/          # Repositorio SQLite
│   ├── downloader/  # Scraper football-data.co.uk + scraper quiniela
│   ├── features/    # Cálculo de ELO, forma reciente, goles esperados
│   ├── model/       # Poisson, Dixon-Coles, ensemble
│   ├── predictions/ # Predictor de jornada + Quinigol
│   └── report/      # Generador HTML + Telegram
├── reports/         # Informes por jornada
├── tests/           # Tests pytest
└── run_jornada.py   # CLI principal
```

## Uso

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 1) Descargar histórico
PYTHONPATH=. python3 -m src.downloader.cli_historico

# 2) Calcular ELO + features
PYTHONPATH=. python3 -m src.features.cli_features

# 3) Predecir jornada actual
PYTHONPATH=. python3 -m src.predictions.cli_jornada --jornada 5
```

## Estado

* Sprint 1: descargador + BD ← EN CURSO