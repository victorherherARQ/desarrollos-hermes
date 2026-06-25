#!/usr/bin/env bash
# ============================================================
# test-from-wsl.sh
# Ejecutar desde WSL para verificar que puede alcanzar al agente.
# Uso: ./test-from-wsl.sh [IP_WINDOWS]
# Si no pasas IP, autodetecta el default gateway de WSL.
# ============================================================
set -e

WIN_IP="${1:-}"
if [[ -z "$WIN_IP" ]]; then
    # La IP del default gateway de WSL suele ser la del host Windows
    WIN_IP=$(ip route | awk '/default/ {print $3; exit}')
    echo "Auto-detected Windows host IP: $WIN_IP"
fi

PORT=8765
BASE="http://$WIN_IP:$PORT"

echo ""
echo "=== Test: $BASE/health ==="
curl -s --max-time 5 "$BASE/health" | head -1
echo ""
echo "=== Test: $BASE/cpu ==="
curl -s --max-time 5 "$BASE/cpu" | head -1
echo ""
echo "=== Test: $BASE/temp ==="
curl -s --max-time 5 "$BASE/temp" | head -1
echo ""
echo "=== Test: $BASE/memory ==="
curl -s --max-time 5 "$BASE/memory" | head -1
echo ""
echo "=== Test: $BASE/arp (devices count) ==="
curl -s --max-time 5 "$BASE/arp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  {len(d)} devices in LAN: {[x[\"ip\"] for x in d[:5]]}...')"
echo ""
echo "=== Test: $BASE/gpu ==="
curl -s --max-time 5 "$BASE/gpu" | head -1
echo ""
echo "All endpoints reachable from WSL."
