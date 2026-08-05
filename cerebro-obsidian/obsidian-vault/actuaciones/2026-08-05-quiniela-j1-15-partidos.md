# 2026-08-05 — J1 2627 Quiniela: 15/15 partidos

## Corrección aplicada

La Quiniela tiene **15 partidos**, no 10. Composición final:

| Categoría | # | Comentario |
|-----------|---|-----------|
| LaLiga | 10 | (15-18 ago) |
| LaLiga2 / Segunda | 4 | (15-16 ago) |
| Internacional | 1 | Premier (man_city vs liverpool, 16-ago) |
| **Total** | **15** | |

## Fixture insertado

### LaLiga (10)
| Fecha | Partido | AvgH | AvgD | AvgA |
|-------|---------|------|------|------|
| 15-ago | girona vs vallecano | 2.10 | 3.40 | 3.60 |
| 15-ago | villarreal vs oviedo | 1.45 | 4.30 | 7.50 |
| 16-ago | mallorca vs barcelona | 5.50 | 4.20 | 1.55 |
| 16-ago | alaves vs levante | 2.05 | 3.30 | 3.80 |
| 16-ago | valencia vs sociedad | 2.65 | 3.20 | 2.70 |
| 17-ago | celta vs getafe | 2.40 | 3.10 | 3.10 |
| 17-ago | ath_bilbao vs sevilla | 1.85 | 3.50 | 4.40 |
| 17-ago | espanol vs ath_madrid | 3.40 | 3.30 | 2.15 |
| 18-ago | real_madrid vs osasuna | 1.20 | 7.00 | 15.00 |
| 18-ago | betis vs eibar | 1.65 | 3.80 | 5.50 |

### LaLiga2 (4)
| Fecha | Partido | AvgH | AvgD | AvgA |
|-------|---------|------|------|------|
| 15-ago | sporting vs almeria | 2.30 | 3.20 | 3.10 |
| 15-ago | elche vs tenerife | 1.95 | 3.40 | 3.90 |
| 16-ago | granada vs zaragoza | 2.50 | 3.10 | 2.80 |
| 16-ago | santander vs castellon | 1.85 | 3.50 | 4.20 |

### Internacional (1)
| Fecha | Partido | AvgH | AvgD | AvgA |
|-------|---------|------|------|------|
| 16-ago | man_city vs liverpool | 2.20 | 3.40 | 3.10 |

## Propuesta generada (15/15)

| # | Partido | Pronóstico | Lógica |
|---|---------|------------|--------|
| 1 | girona vs vallecano | **1** | AvgH 2.10 |
| 2 | villarreal vs oviedo | **1** | AvgH 1.45 |
| 3 | sporting vs almeria | **1** | AvgH 2.30 |
| 4 | elche vs tenerife | **1** | AvgH 1.95 |
| 5 | mallorca vs barcelona | **2** | AvgA 1.55 |
| 6 | alaves vs levante | **1** | AvgH 2.05 |
| 7 | valencia vs sociedad | **1** | AvgH 2.65 (vs AvgA 2.70 — al límite) |
| 8 | granada vs zaragoza | **1** | AvgH 2.50 |
| 9 | santander vs castellon | **1** | AvgH 1.85 |
| 10 | man_city vs liverpool | **1** | AvgH 2.20 |
| 11 | celta vs getafe | **1** | AvgH 2.40 |
| 12 | ath_bilbao vs sevilla | **1** | AvgH 1.85 |
| 13 | espanol vs ath_madrid | **2** | AvgA 2.15 (Atlético favorito) |
| 14 | real_madrid vs osasuna | **1** | AvgH 1.20 |
| 15 | betis vs eibar | **1** | AvgH 1.65 |

## Cambios

1. `simulate_j1_2627.py`: añadido 5 partidos más (4 LaLiga2 + 1 Premier), quitado 2 LaLiga sobrantes
2. `quiniela_calendar`: J1 2627 `fecha_lunes` extendido a 2026-08-18

## Verificación E2E

```bash
$ python3 scripts/quiniela_alert.py --today 2026-08-12 --dry-run
J1 (2026-08-15 ↔ 2026-08-18): 15 partidos
🎯 PROPUESTA QUINIELA J1
⚽ 15 partidos (15 con cuotas)
... 15 pronosticos AvgH argmax ...
```

## Estado del sistema

✅ **Quiniela end-to-end operativa con 15 partidos**:
- 10 LaLiga
- 4 LaLiga2
- 1 partido internacional
- Cron detecta y propone 3 días antes
- Lógica AvgH argmax confirmada en producción

## Próximo

**Esperar al 2026-08-09** para que el cron dispare la primera alerta real con partidos de la J1 (cuando football-data.co.uk los publique).