# ============================================================
# scripts/diagnose.ps1
# Diagnostica por qué el agente no arranca.
# ============================================================

Write-Host "=== DIAGNÓSTICO DEL AGENTE ===" -ForegroundColor Cyan
Write-Host ""

# 1. ¿Qué `python` resuelve Windows?
Write-Host "[1] ¿Dónde está python?" -ForegroundColor Yellow
foreach ($c in @("py", "python", "python3")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "    $c -> $($cmd.Source)"
    } else {
        Write-Host "    $c -> (no encontrado)"
    }
}
Write-Host ""

# 2. ¿El stub de Microsoft Store funciona?
Write-Host "[2] Probando 'python --version'..." -ForegroundColor Yellow
try {
    $ver = & python --version 2>&1
    Write-Host "    Salida: $ver" -ForegroundColor Green
} catch {
    Write-Host "    [ERROR] $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# 3. Estado de la tarea programada
Write-Host "[3] Estado de la Scheduled Task..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName "WindowsAgent-Monitor-Hardware" -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "    Estado: $($task.State)"
    Write-Host "    Última ejecución: $($task.LastRunTime)"
    Write-Host "    Resultado última: $($task.LastTaskResult)"
} else {
    Write-Host "    Tarea no encontrada" -ForegroundColor Red
}
Write-Host ""

# 4. ¿Hay algo en el puerto 8765?
Write-Host "[4] Puerto 8765..." -ForegroundColor Yellow
$conn = Test-NetConnection -ComputerName localhost -Port 8765 -WarningAction SilentlyContinue
if ($conn.TcpTestSucceeded) {
    Write-Host "    [OK] Algo escucha en :8765" -ForegroundColor Green
} else {
    Write-Host "    [VACÍO] Nada escucha en :8765" -ForegroundColor Red
}
Write-Host ""

# 5. ¿Hay un agente ejecutándose?
Write-Host "[5] Procesos python corriendo..." -ForegroundColor Yellow
$procs = Get-Process python -ErrorAction SilentlyContinue
if ($procs) {
    foreach ($p in $procs) {
        Write-Host "    PID $($p.Id) - iniciado: $($p.StartTime)"
    }
} else {
    Write-Host "    [NO] Ningún python corriendo" -ForegroundColor Red
}
Write-Host ""

# 6. Logs
Write-Host "[6] Logs del agente (si existen)..." -ForegroundColor Yellow
$logsDir = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "logs"
if (Test-Path $logsDir) {
    Get-ChildItem $logsDir -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "    $($_.Name) ($($_.Length) bytes)"
    }
} else {
    Write-Host "    (carpeta logs/ no existe)"
}
Write-Host ""

Write-Host "=== FIN DIAGNÓSTICO ===" -ForegroundColor Cyan
