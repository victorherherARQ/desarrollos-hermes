#!/usr/bin/env bash
# Backup de las DBs de Network Monitor
# Uso: ./scripts/backup.sh   (ejecutar desde la raíz del proyecto)
set -euo pipefail

BACKUP_DIR="./backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "→ Backup en $BACKUP_DIR"

# Prometheus
docker exec nm-prometheus tar czf - /prometheus > "$BACKUP_DIR/prometheus.tar.gz" 2>/dev/null || echo "  ⚠️ Prometheus no accesible"

# Grafana
docker exec nm-grafana tar czf - /var/lib/grafana > "$BACKUP_DIR/grafana.tar.gz" 2>/dev/null || echo "  ⚠️ Grafana no accesible"

# LAN scanner (SQLite)
if [ -f ./lan-scanner/data/scanner.db ]; then
  sqlite3 ./lan-scanner/data/scanner.db ".backup '$BACKUP_DIR/scanner.db'" 2>/dev/null \
    || cp ./lan-scanner/data/scanner.db "$BACKUP_DIR/scanner.db"
  echo "  ✓ scanner.db"
fi

# Alertmanager
docker exec nm-alertmanager tar czf - /alertmanager > "$BACKUP_DIR/alertmanager.tar.gz" 2>/dev/null || echo "  ⚠️ Alertmanager no accesible"

echo "✓ Backup completado: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
