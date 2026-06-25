# System Monitor

Monitor de sistema para WSL2: CPU, RAM, disco, red, procesos, contenedores Docker, histórico con SQLite y UI web con gráficas.

**Limitación importante**: WSL2 es una VM Hyper-V y **no expone temperatura de CPU/GPU ni ventiladores**. Ver `LIMITACIONES.md` para la solución.

## Stack

| Componente | Tecnología |
|---|---|
| Recolector | Python 3.11 + psutil + APScheduler |
| API | FastAPI |
| UI | HTML + Canvas (sin frameworks) |
| Histórico | SQLite (30 días) |
| Métricas Prometheus | `/metrics` endpoint |
| Contenedores | Docker socket (read-only) |

## Servicios

| Servicio | Puerto |
|---|---|
| UI | 8500 |
| Prometheus | 9100 (opcional) |

## Arrancar

```bash
cd /home/vhdez/desarrollos-hermes/system-monitor
cp .env.example .env
docker compose up -d
open http://localhost:8500
```

## API

- `GET /api/health` - healthcheck
- `GET /api/current` - snapshot actual
- `GET /api/history?hours=24` - histórico
- `GET /api/containers` - contenedores Docker
- `GET /api/report?hours=24` - informe con min/avg/max
- `GET /metrics` - Prometheus
