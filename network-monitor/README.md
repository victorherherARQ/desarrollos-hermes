# Network Monitor (Fing-style)

Monitor de red local con UI web: descubrimiento de dispositivos, velocidad up/down, métricas de tráfico y alertas.

Inspirado en [Fing](https://www.fing.com/es/) pero open source y auto-hospedado.

## Stack

- **Prometheus** (9090) — almacenamiento de series temporales
- **node_exporter** (9100) — métricas de sistema
- **speedtest-exporter** (9798) — velocidad de internet
- **Grafana** (3000) — dashboards
- **lan-scanner** (8000) — descubrimiento ARP/nmap + API + UI
- **Alertmanager** (9093) — alertas vía Telegram/email

## Arrancar

```bash
cd /home/vhdez/desarrollos-hermes/network-monitor
docker compose up -d
```

## Acceso

| URL | Qué ves |
|---|---|
| http://localhost:3000 | Grafana (dashboards) |
| http://localhost:8000 | UI del scanner (dispositivos + velocidad) |
| http://localhost:9090 | Prometheus (consultas técnicas) |
| http://localhost:9093 | Alertmanager (alertas activas) |

## Credenciales

- Grafana: admin / `GRAFANA_ADMIN_PASSWORD` en `.env`

## Estructura

```
.
├── docker-compose.yaml
├── .env.example
├── prometheus/
│   ├── prometheus.yml
│   └── alerts.yml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasource.yml
│   │   └── dashboards/dashboard.yml
│   └── dashboards/
│       ├── network-overview.json
│       └── speedtest.json
├── alertmanager/
│   └── alertmanager.yml
├── lan-scanner/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── scanner.py
│   ├── db.py
│   └── static/
│       ├── index.html
│       └── app.js
└── scripts/
    └── backup.sh
```
