# 🪟 Windows Agent — Guía de instalación

Esta guía es para instalar el agente en **Windows** (no WSL). El agente expone por HTTP el hardware que WSL2 no puede ver, y los stacks de WSL lo consumen.

## 📋 Requisitos

| Requisito | Versión |
|---|---|
| Windows | 10 u 11 (64 bits) |
| Python | 3.8 o superior |
| Permisos | Administrador (solo para abrir firewall e instalar la tarea) |
| Red | El puerto 8765 debe estar libre |

## 🚀 Instalación paso a paso

### 1. Instalar Python (si no lo tienes)

1. Ve a https://www.python.org/downloads/
2. Descarga Python 3.11 o 3.12
3. **MUY IMPORTANTE**: marca la casilla "Add Python to PATH" al inicio de la instalación
4. Finaliza la instalación

Verificar abriendo PowerShell y ejecutando:
```powershell
python --version
# Debe decir algo como: Python 3.11.9
```

### 2. Copiar el agente a Windows

Los archivos del agente están en WSL. Tienes dos opciones:

**Opción A — Copiar con el explorador de archivos**:
1. Abre el explorador de Windows
2. En la barra de direcciones escribe: `\\wsl$\Ubuntu\home\vhdez\desarrollos-hermes\windows-agent\`
3. Selecciona todo (Ctrl+A), copia (Ctrl+C)
4. Ve a `C:\Users\vhdez\desarrollos-hermes\` y pega la carpeta `windows-agent` ahí

**Opción B — Desde PowerShell** (más rápido):
```powershell
$src = "\\wsl$\Ubuntu\home\vhdez\desarrollos-hermes\windows-agent"
$dst = "$env:USERPROFILE\desarrollos-hermes\windows-agent"
New-Item -ItemType Directory -Path $dst -Force
Copy-Item -Path "$src\*" -Destination $dst -Recurse
Write-Host "Copiado a: $dst"
```

### 3. Abrir el puerto en el firewall de Windows

**Como Administrador** (clic derecho en PowerShell → "Ejecutar como administrador"):
```powershell
cd "$env:USERPROFILE\desarrollos-hermes\windows-agent"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\allow-firewall.ps1
```

Debe decir: `Regla creada.`

### 4. Registrar el agente como tarea programada

Esto hace que el agente:
- Arranque automáticamente cuando inicies sesión en Windows
- Se reinicie solo si se cae
- No muestre ventana de consola

**Como Administrador** (la misma ventana del paso 3):
```powershell
cd "$env:USERPROFILE\desarrollos-hermes\windows-agent"
.\scripts\install-task.ps1
```

Debe decir al final: `Agente respondiendo: {"ok":true,"ts":...}`

### 5. Probar que funciona

**Desde Windows** (cualquier PowerShell):
```powershell
curl http://localhost:8765/health
curl http://localhost:8765/temp
curl http://localhost:8765/arp
```

**Desde WSL**:
```bash
cd /home/vhdez/desarrollos-hermes/windows-agent
./test-from-wsl.sh
```

Debe listar las IPs de los dispositivos de tu LAN.

## 📡 Endpoints que expone

| URL | Devuelve |
|---|---|
| `http://localhost:8765/` | Página HTML con enlaces |
| `http://localhost:8765/health` | `{"ok":true,"ts":...}` |
| `http://localhost:8765/all` | Todo en JSON |
| `http://localhost:8765/temp` | Temperatura CPU real |
| `http://localhost:8765/cpu` | Info CPU + temp |
| `http://localhost:8765/memory` | RAM total/usada |
| `http://localhost:8765/gpu` | GPUs |
| `http://localhost:8765/processes` | Top procesos |
| `http://localhost:8765/arp` | **Tabla ARP de tu LAN real** |
| `http://localhost:8765/interfaces` | Interfaces de red |
| `http://localhost:8765/metrics` | Prometheus text format |

## 🔧 Comandos útiles

```powershell
# Ver si la tarea está corriendo
Get-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware"

# Iniciar manualmente
Start-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware"

# Detener
Stop-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware"

# Desinstalar completamente
cd "$env:USERPROFILE\desarrollos-hermes\windows-agent"
.\scripts\uninstall-task.ps1

# Ver logs
Get-Content "$env:USERPROFILE\desarrollos-hermes\windows-agent\logs\agent.log" -Tail 50
```

## ❓ Problemas frecuentes

### El agente no arranca

- Verifica que Python está en PATH: `python --version`
- Ejecuta manualmente para ver errores: `cd $env:USERPROFILE\desarrollos-hermes\windows-agent ; python agent.py`
- Mira los logs en `logs/`

### La temperatura devuelve `null`

La API WMI `MSAcpi_ThermalZoneTemperature` no funciona en todos los sistemas (especialmente laptops modernas que usan EC firmware propio). Soluciones:

1. **OpenHardwareMonitor** (gratis): https://openhardwaremonitor.org/ — instálalo, déjalo corriendo, el agente lo detectará automáticamente
2. **HWiNFO64** con sensor compartido: https://www.hwinfo.com/
3. **Speccy** + script personalizado

### WSL no puede conectarse

1. Verifica el firewall:
   ```powershell
   Get-NetFirewallRule -DisplayName "WindowsAgent-Monitor-Hardware"
   ```
   Si no existe, repite el paso 3.

2. Encuentra la IP de Windows desde WSL:
   ```bash
   ip route | awk '/default/ {print $3}'
   ```

3. Prueba con esa IP:
   ```bash
   ./test-from-wsl.sh 172.29.48.1
   ```

### El firewall me pide confirmación extra

En Windows 11, al instalar la regla puede salir un popup del UAC (control de cuentas). Acepta.

## 🔄 Actualizar el agente

Si modificas `agent.py` en WSL, vuelve a copiarlo a Windows (paso 2) y reinicia la tarea:
```powershell
Stop-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware"
Start-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware"
```

## 📁 Estructura final

```
C:\Users\vhdez\desarrollos-hermes\windows-agent\
├── agent.py
├── run.bat
├── run-hidden.vbs
├── test-from-wsl.sh
├── requirements.txt
├── README.md
├── scripts\
│   ├── install-task.ps1
│   ├── uninstall-task.ps1
│   └── allow-firewall.ps1
└── logs\
```
