---
fecha_creada: 2026-08-03
fecha_cierre: 2026-08-06
prioridad: alta
persona: Victor
proyecto: quiniela-analyzer
fecha_limite: ""
tags: [tarea/hecha]
---

# ~~Ver siguiente paso de quiniela-analyzer~~ (CERRADA)

> **Cerrada 2026-08-06** — Plan quiniela v3-v7 cerrado definitivamente (todos NO-GO vs AvgH 50.12%). No proseguir sin orden explícita.

## Decisión tomada

- Plan v3-v7 NO-GO confirmado en 7 iteraciones
- AvgH (mercado) es techo con datos públicos
- Sin nueva fuente de datos no hay ROI de continuar
- **Acción**: cerrar definitivamente
- Próxima decisión pendiente: si surgen CSVs reales de 2026-27, refrescar BD manualmente

## Histórico del proyecto

- v2 (julio 2026): 68 features, val acc 46.22% vs 46.88% baseline
- v3 (agosto 2026): cuotas + forma + h2h + fatiga → 50.51% (no Go)
- v4: ensemble → no mejora
- v5: xG_proxy + ELO → +0.04pp (no Go)
- v6: xG StatsBomb real → +0.17pp (no Go)
- v7: AvgH probs → -0.74pp (no Go)
- **Conclusión**: mercado AvgH ya incorpora toda la info pública

## Sistema de avisos

Sigue operativo independientemente (cron `quiniela-alert-diario`, id `2f02d434e409`).
No se cierra.
