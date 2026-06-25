# 🪟 Windows Agent

Agente Python para Windows que expone por HTTP el hardware que WSL2 no puede ver:

- 🌡️ **Temperatura CPU** (WMI MSAcpi_ThermalZoneTemperature)
- 🔥 **Carga CPU** real de Windows (no del namespace de WSL)
- 🧠 **RAM** total/usada/porcentaje
- 🎮 **GPUs** (WMI Win32_VideoController)
- 🖥️ **Top procesos** con PID, usuario, CPU, RAM
- 🌐 **Tabla ARP** real — los dispositivos de tu LAN que WSL no ve
- 📡 **Interfaces de red** de Windows

WSL consume esto y lo muestra en sus dashboards.

## 📦 Estructura

```
windows-agent/
├── agent.py                  # el corazón: HTTP server + lectores WMI/Win32
├── run.bat                   # arranque en consola
├── run-hidden.vbs            # arranque sin ventana
├── test-from-wsl.sh          # smoke test desde WSL
├── requirements.txt          # (vacío: solo stdlib)
├── scripts/
│   ├── install-task.ps1      # instala como Scheduled Task (auto-arranque)
│   ├── uninstall-task.ps1
│   └── allow-firewall.ps1    # abre el puerto 8765
└── logs/                     # salida del agente
```

## 🚀 Instalación (3 pasos)

### 1. Instala Python 3.8+ en Windows
- [python.org](https://www.python.org/downloads/) → "Add Python to PATH"

### 2. Abre el puerto en el firewall (PowerShell como Administrador)
```powershell
cd C:\path\a\windows-agent\scripts
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\allow-firewall.ps1
```

### 3. Registra el agente como tarea programada (auto-arranque con Windows)
```powershell
cd C:\path\a\windows-agent
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install-task.ps1
```

Eso es todo. El agente:
- Arranca cuando inicias sesión en Windows
- Se reinicia si se cae
- No muestra ventana de consola
- Responde en `http://<ip-windows>:8765/`

## 🌐 Endpoints

| URL | Devuelve |
|---|---|
| `GET /` | UI HTML con enlaces |
| `GET /health` | `{"ok":true,"ts":...}` |
| `GET /all` | JSON con todo |
| `GET /temp` | `{"temp_cpu_c": 47.5, "ts":...}` |
| `GET /cpu` | info CPU + temp |
| `GET /memory` | RAM |
| `GET /gpu` | lista GPUs |
| `GET /processes` | top procesos |
| `GET /arp` | tabla ARP (LAN real) |
| `GET /interfaces` | interfaces de red |
| `GET /metrics` | Prometheus text format |

## 🐚 Probar desde WSL

```bash
# Autodetecta la IP de Windows (default gateway de WSL)
./test-from-wsl.sh

# O pásala manual
./test-from-wsl.sh 192.168.1.100
```

## 🔌 Integración con los stacks WSL

### system-monitor
WSL puede enriquecer sus métricas con:
```python
import urllib.request, json
windows = json.loads(urllib.request.urlopen("http://172.29.48.1:8765").read())
temp = windows["temp_cpu_c"]     # ← temperatura REAL
arp_count = len(windows["arp"])  # ← dispositivos LAN reales
```

### network-monitor
El `lan-scanner` puede fusionar ARP-scan (limitado en WSL) con tabla ARP de Windows (real).

## 🔧 Troubleshooting

**El agente no responde desde WSL**
1. Verifica que el agente arrancó: en Windows, abre `http://localhost:8765/health` en el navegador
2. Si local funciona pero WSL no → ejecuta `.\scripts\allow-firewall.ps1` como Administrador
3. Encuentra la IP de Windows desde WSL: `ip route | awk '/default/ {print $3}'` (suele ser la del host)

**La temperatura devuelve `null`**
- WMI `MSAcpi_ThermalZoneTemperature` no funciona en todos los sistemas
- Solución: instala [OpenHardwareMonitor](https://openhardwaremonitor.org/) y deja el daemon WMI encendido
- El agente lo detectará automáticamente

**PowerShell tarda mucho**
- Las llamadas WMI pueden tardar 1-2s la primera vez (caché fría). Las siguientes son rápidas.

## 🗑️ Desinstalar

```powershell
cd C:\path\a\windows-agent
.\scripts\uninstall-task.ps1
```
