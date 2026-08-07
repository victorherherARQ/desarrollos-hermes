# 2026-08-07 — Quiniela J1 oficial publicada por LAE

## ✅ Logrado

**LAE ya publicó la quiniela oficial del 16-ago-2026** (cierre del finde de LaLiga J1).

**15 partidos OFICIALES** (distintos a mi propuesta sintética anterior):

| # | Local | Visitante |
|---|-------|-----------|
| 1 | Alavés | Getafe B |
| 2 | **Sevilla Ath.** | **Rayo Vallecano** |
| 3 | Racing De Santander | Villarreal B |
| 4 | Espanyol B | Levante B |
| 5 | R.C. Celta B | Osasuna B |
| 6 | Andorra | Ceuta |
| 7 | Cádiz | Fortuna Sittard |
| 8 | R. Oviedo | Granada Femenino |
| 9 | Mallorca B | Valladolid B |
| 10 | Eibar Femenino | Tenerife B |
| 11 | Burgos | Córdoba |
| 12 | Girona | Leganés |
| 13 | Las Palmas B | Albacete |
| 14 | Sporting B | Sabadell |
| 15 | Deportivo B | Elche |

## 🔧 Componentes nuevos

### 1. `scripts/quiniela_lae_official.py`
**Scraper oficial de LAE** (vía mirror [combinacionganadora.com](https://www.combinacionganadora.com/quiniela/resultados/YYYY-MM-DD/) porque loteriasyapuestas.es anti-bot nos bloquea).

```bash
python3 scripts/quiniela_lae_official.py --jornada 2026-08-16
```

Guarda en tabla `lae_quiniela` (15 partidos por jornada).

### 2. `scripts/team_name_map.py`
**Mapa de normalización**: equipo LAE (e.g. "R.C. Celta B") → nombre BD (e.g. "celta").

Inventario de todos los equipos LaLiga + filiales conocidos.

### 3. `scripts/quiniela_proposal_lae.py`
**Genera propuesta USANDO DATOS REALES** de cada equipo en la temporada 2526.

```bash
python3 scripts/quiniela_proposal_lae.py --jornada 2026-08-15
```

Método: PPG histórico → si `diff > 0.3` → 1, `diff < -0.3` → 2, else X.

### 4. `scripts/quiniela_alert.py` actualizado
**3 estados de aviso**:
- **Estado 0** (LAE no publicado): silencio
- **Estado 1** (LAE ok, no propuesta): aviso ALTA "pídemela"
- **Estado 2** (LAE ok, propuesta desactualizada): aviso MEDIA "regenera"
- **Estado 3** (todo al día): silencio

## 📊 Quiniela final J1 2627 (15 partidos)

| # | Local | Visitante | Pronóstico | Prob H/D/A |
|---|-------|-----------|:---:|:---:|
| 1 | Alavés | Getafe B | **X** | 35/35/30 |
| 2 | Sevilla Ath. | Rayo Vallecano | **X** | 35/35/30 |
| 3 | Racing De Santander | Villarreal B | **X** | 35/35/30 |
| 4 | Espanyol B | Levante B | **X** | 35/35/30 |
| 5 | R.C. Celta B | Osasuna B | **1** | 55/25/20 |
| 6 | Andorra | Ceuta | **X** | 35/35/30 |
| 7 | Cádiz | Fortuna Sittard | **1** | 45/30/25 |
| 8 | R. Oviedo | Granada Femenino | **2** | 20/25/55 |
| 9 | Mallorca B | Valladolid B | **X** | 35/35/30 |
| 10 | Eibar Femenino | Tenerife B | **1** | 45/30/25 |
| 11 | Burgos | Córdoba | **X** | 35/35/30 |
| 12 | Girona | Leganés | **X** | 35/35/30 |
| 13 | Las Palmas B | Albacete | **1** | 55/25/20 |
| 14 | Sporting B | Sabadell | **1** | 45/30/25 |
| 15 | Deportivo B | Elche | **1** | 55/25/20 |

**Distribución**: 1=7, X=7, 2=1

## ⚠️ Advertencias

1. **Sin cuotas reales**: las AvgH/probs son **derivadas de PPG histórico**, no cuotas de bookmaker. Cuando bookmakers publiquen (mayo 1-2 días antes), habría que actualizar.
2. **Equipos sin histórico**: Fortuna Sittard, Tenerife B, Sabadell no están en BD 2526. Se usa heurística: `local favorito`.
3. **Lógica simple**: no contempla factor local, fatiga Champions, etc.

## 📦 Commits

```
91b3333 feat(quiniela): scraper oficial quiniela LAE (mirror combinacionganadora.com)
```

(próximos: alert.py actualizado, proposal_lae.py, team_name_map.py)
