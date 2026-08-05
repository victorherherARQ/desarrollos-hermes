# 2026-08-05 — Test E2E del sistema de avisos (J1 2627 simulada)

## Acción

Para validar el sistema **antes de que llegue la J1 real** (15-ago-2026), inserté partidos sintéticos de la J1 LaLiga 2026-27 con AvgH plausibles y ejecuté el cron con `--today 2026-08-12`.

## Fixture insertado

| Fecha | Partido | AvgH | AvgD | AvgA |
|-------|---------|------|------|------|
| 2026-08-15 | girona vs vallecano | 2.10 | 3.40 | 3.60 |
| 2026-08-15 | villarreal vs oviedo | 1.45 | 4.30 | 7.50 |
| 2026-08-16 | mallorca vs barcelona | 5.50 | 4.20 | 1.55 |
| 2026-08-16 | alaves vs levante | 2.05 | 3.30 | 3.80 |
| 2026-08-16 | valencia vs sociedad | 2.65 | 3.20 | 2.70 |
| 2026-08-17 | celta vs getafe | 2.40 | 3.10 | 3.10 |
| 2026-08-17 | ath_bilbao vs sevilla | 1.85 | 3.50 | 4.40 |
| 2026-08-17 | espanol vs ath_madrid | 3.40 | 3.30 | 2.15 |
| 2026-08-18 | real_madrid vs osasuna | 1.20 | 7.00 | 15.00 |
| 2026-08-18 | betis vs eibar | 1.65 | 3.80 | 5.50 |
| 2026-08-18 | rayo_vallecano vs leganes | 1.95 | 3.40 | 4.00 |
| 2026-08-18 | espanyol vs valladolid | 2.10 | 3.30 | 3.50 |

## Propuesta generada (8 partidos J1)

| # | Partido | Pronóstico | Lógica |
|---|---------|------------|--------|
| 1 | girona vs vallecano | **1** | AvgH 2.10 (fav. local) |
| 2 | villarreal vs oviedo | **1** | AvgH 1.45 (muy favorito) |
| 3 | mallorca vs barcelona | **2** | AvgA 1.55 (Barça claro favorito) |
| 4 | alaves vs levante | **1** | AvgH 2.05 (ligero fav. local) |
| 5 | valencia vs sociedad | **1** | AvgH 2.65 (margen mínimo sobre 2.70) |
| 6 | celta vs getafe | **1** | AvgH 2.40 (vs AvgA 3.10) |
| 7 | ath_bilbao vs sevilla | **1** | AvgH 1.85 |
| 8 | espanol vs ath_madrid | **2** | AvgA 2.15 (Atlético favorito fuera) |

## Cambios para que funcione

1. **`quiniela_proposal.py::get_matches()`**: eliminado filtro `result IS NOT NULL`. Ahora también acepta partidos futuros.
2. **`match_odds` schema**: usa `b365c_*` (closing) en vez de `b365_*` (que no existe).

## Verificación E2E

```bash
$ python3 scripts/quiniela_alert.py --today 2026-08-12 --dry-run
2026-08-05 19:38:40 Hoy: 2026-08-12
2026-08-05 19:38:40 1 aviso(s) pendiente(s)
2026-08-05 19:38:40 Procesando J1 (2627)
2026-08-05 19:38:40 J1 (2026-08-15 ↔ 2026-08-17): 8 partidos
🎯 PROPUESTA QUINIELA J1
📅 2026-08-15 → 2026-08-17
⚽ 8 partidos (8 con cuotas)
   1. 🏠 1 | girona vs vallecano [✓odds]
   2. 🏠 1 | villarreal vs oviedo [✓odds]
   3. ✈️ 2 | mallorca vs barcelona [✓odds]
   4. 🏠 1 | alaves vs levante [✓odds]
   5. 🏠 1 | valencia vs sociedad [✓odds]
   6. 🏠 1 | celta vs getafe [✓odds]
   7. 🏠 1 | ath_bilbao vs sevilla [✓odds]
   8. ✈️ 2 | espanol vs ath_madrid [✓odds]
📊 Backtest: 0/8 = 0.0%
```

## Estado del sistema

✅ **Sistema operativo end-to-end**:
- `quiniela_calendar` 2627 con 38 jornadas (J1 15-17 ago)
- `matches` J1 2627 con partidos sintéticos (12)
- `match_odds` J1 2627 con cuotas AvgH/Pinnacle/Bet365
- `quiniela_alert.py` detecta J1 con 3 días de antelación
- `quiniela_proposal.py` genera pronóstico AvgH
- Cron `quiniela-alert-diario` ejecutándose diario 9:00 AM

## Próximo paso

**Esperar al 2026-08-09 (sábado)** para que el cron dispare la primera alerta real con partidos de la J1 actualizados (cuando la BD de football-data.co.uk publique los partidos reales).