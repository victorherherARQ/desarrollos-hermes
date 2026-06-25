# ============================================================
# scripts/install-task.ps1
# Registra el agente como tarea programada.
# Versión robusta: detecta Python evitando el stub de Microsoft Store.
#
# Uso (PowerShell como Administrador):
#   cd C:\path\a\windows-agent
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\install-task.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$taskName = "WindowsAgent-Monitor-Hardware"

Write-Host "[1/5] Buscando Python real (evitando el stub de Microsoft Store)..." -ForegroundColor Cyan

# Candidatos en orden de preferencia: el Python real, NO el stub de WindowsApps
$candidates = @(
    "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.13-64\python.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.12-64\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "C:\Python314\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe",
    "C:\Program Files\Python314\python.exe",
    "C:\Program Files\Python313\python.exe",
    "C:\Program Files\Python312\python.exe"
)

$python = $null
foreach ($exe in $candidates) {
    if (Test-Path $exe) {
        # Verificar que NO es el stub de Microsoft Store
        $resolved = (Resolve-Path $exe).Path
        if ($resolved -notmatch "WindowsApps") {
            $python = $resolved
            break
        }
    }
}

# Si nada de lo anterior funciona, buscar 'py' launcher y dejarle elegir
if (-not $python) {
    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        $pyReal = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($pyReal -and $pyReal -notmatch "WindowsApps") {
            $python = $pyReal.Trim()
        }
    }
}

if (-not $python) {
    Write-Host "  [ERROR] Python real no encontrado." -ForegroundColor Red
    Write-Host "  Instala Python desde python.org marcando 'Add to PATH'." -ForegroundColor Red
    Write-Host "  Luego abre un PowerShell NUEVO y vuelve a ejecutar este script." -ForegroundColor Red
    exit 1
}

Write-Host "  Python: $python" -ForegroundColor Green
$ver = & $python --version 2>&1
Write-Host "  Version: $ver" -ForegroundColor Green

Write-Host "[2/5] Comprobando puerto 8765 libre..." -ForegroundColor Cyan
$listener = New-Object System.Net.Sockets.TcpClient
try {
    $listener.Connect("127.0.0.1", 8765)
    $listener.Close()
    Write-Host "  [WARN] Puerto 8765 ya esta en uso. Deten el proceso antes de continuar." -ForegroundColor Yellow
    $confirm = Read-Host "  Continuar igualmente? (s/N)"
    if ($confirm -ne "s" -and $confirm -ne "S") { exit 1 }
} catch {
    Write-Host "  Puerto libre." -ForegroundColor Green
}

Write-Host "[3/5] Registrando Scheduled Task '$taskName'..." -ForegroundColor Cyan

# Borrar tarea previa si existe (para empezar limpio)
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false | Out-Null
    Write-Host "  Tarea previa eliminada." -ForegroundColor Yellow
}

$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $root + '\agent.py"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "  Tarea registrada." -ForegroundColor Green

Write-Host "[4/5] Iniciando agente..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 4

# Test
$ok = $false
try {
    $r = Invoke-WebRequest "http://localhost:8765/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "  [OK] Agente respondiendo: $($r.Content)" -ForegroundColor Green
    $ok = $true
} catch {
    Write-Host "  [WARN] Agente no responde todavia. Reintentando en 3s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    try {
        $r = Invoke-WebRequest "http://localhost:8765/health" -UseBasicParsing -TimeoutSec 5
        Write-Host "  [OK] Agente respondiendo: $($r.Content)" -ForegroundColor Green
        $ok = $true
    } catch {
        Write-Host "  [ERROR] Agente sigue sin responder." -ForegroundColor Red
        Write-Host "  Mira los logs en: $root\logs\" -ForegroundColor Yellow
        Write-Host "  O ejecuta manualmente: $python `"$root\agent.py`"" -ForegroundColor Yellow
    }
}

Write-Host "[5/5] Resultado final..." -ForegroundColor Cyan
if ($ok) {
    Write-Host ""
    Write-Host "=== AGENTE ACTIVO EN http://localhost:8765 ===" -ForegroundColor Green
    Write-Host "  Endpoints:" -ForegroundColor Cyan
    Write-Host "    http://localhost:8765/health     - status"
    Write-Host "    http://localhost:8765/system     - CPU temp + RAM + load"
    Write-Host "    http://localhost:8765/arp        - dispositivos LAN"
    Write-Host "    http://localhost:8765/network    - adaptadores de red"
    Write-Host "    http://localhost:8765/top        - top procesos"
    Write-Host "    http://localhost:8765/all        - todo combinado"
    Write-Host ""
    Write-Host "  Para que WSL pueda leerlo, Victor debe ejecutar desde WSL:" -ForegroundColor Yellow
    Write-Host "    curl http://$(hostname):8765/system" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "=== AGENTE NO RESPONDE ===" -ForegroundColor Red
    Write-Host "  Diagnostico:" -ForegroundColor Yellow
    Write-Host "    Get-ScheduledTask -TaskName '$taskName'"
    Write-Host "    Get-Process python"
    Write-Host "    Get-Content '$root\logs\*.log' -ErrorAction SilentlyContinue"
}

Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor Cyan
Write-Host "  Iniciar:    Start-ScheduledTask -TaskName '$taskName'"
Write-Host "  Detener:    Stop-ScheduledTask  -TaskName '$taskName'"
Write-Host "  Ver logs:   Get-Content '$root\logs\agent.log' -Tail 50 -Wait"
Write-Host "  Desinstalar: .\scripts\uninstall-task.ps1"
