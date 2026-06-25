# Euromillones Analyzer

Analisis estadistico de todos los sorteos historicos de Euromillones con backtesting riguroso.

## Datos
- 1951 sorteos (2004-02-13 a 2026-06-23)
- Fuente: [daowa89/lottery-archive](https://github.com/daowa89/lottery-archive) (GitHub)
- Formato CSV: `date,n1,n2,n3,n4,n5,s1,s2`

## Acercamientos aplicados

1. **Segmentacion por anios** - 5 bloques temporales
2. **Ventanas moviles** - rolling windows de 200 sorteos
3. **Markov / memoria** - runs test + autocorrelacion
4. **Tests de aleatoriedad formales** - chi², KS, Bartels, entropia
5. **Entropia / informacion mutua** - I(A;B) entre numeros y sumas
6. **Bayesiano** - posterior Beta-binomial + validacion en test

## Resultado global

**Euromillones es estadísticamente indistinguible de azar genuino.**
- Entropia: 99.93% del maximo (numeros)
- Memoria entre sorteos: ~0
- Informacion mutua entre numeros: ~0 bits
- **Unico patron real persistente**: el numero 22 sale consistentemente menos (-16% train, -34% test)

## Estructura
```
├── data/             # SQLite + CSV crudo
├── src/
│   ├── db/          # Repository SQLite
│   ├── downloader/  # Scraper + validador
│   └── analysis/    # Descriptivo, patrones, backtest
├── reports/
│   ├── INFORME_FINAL.md          # Primer informe
│   ├── INFORME_CONSOLIDADO.md    # Indice de los 6 acercamientos
│   └── informes/                  # 6 informes individuales (.md + .json)
├── tests/           # 23 tests pytest
├── run_phase3.py    # Ejecuta Fase 3 (analisis descriptivo)
├── run_phase6.py    # Ejecuta Fase 6 (backtesting)
├── run_approach_*.py # Ejecuta cada uno de los 6 acercamientos
├── docs/            # Documentacion
└── requirements.txt
```

## Uso

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Pipeline completo
PYTHONPATH=. python3 -c "
from src.db.repository import SorteoRepository
from src.downloader.scraper import pipeline_descarga
pipeline_descarga(SorteoRepository('data/euromillones.db'))
"

# Tests
pytest tests/ -v

# Acercamientos
python3 run_approach_01_yearly_segmentation.py
python3 run_approach_02_rolling_windows.py
python3 run_approach_03_markov_runs.py
python3 run_approach_04_randomness_tests.py
python3 run_approach_05_entropy_mi.py
python3 run_approach_06_bayesian.py
```

## Ver informes

- [reports/INFORME_CONSOLIDADO.md](reports/INFORME_CONSOLIDADO.md) — indice de todo
- [reports/INFORME_FINAL.md](reports/INFORME_FINAL.md) — primer informe
- [reports/informes/](reports/informes/) — 6 informes individuales (.md) + JSON detallado

## Conclusion

**No usar patrones para jugar.** El unico patron real (numero 22 con sesgo negativo) tiene impacto economico despreciable: probabilidad de ganar sigue siendo ~1 en 139.838.160.
