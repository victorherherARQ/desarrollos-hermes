# ============================================================
# scripts/uninstall-task.ps1
# ============================================================
$taskName = "WindowsAgent-Monitor-Hardware"

Write-Host "Deteniendo y eliminando tarea '$taskName'..." -ForegroundColor Cyan
try {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Hecho." -ForegroundColor Green
} catch {
    Write-Host "No se encontró la tarea (¿ya estaba desinstalada?)." -ForegroundColor Yellow
}

# Matar el agente si está corriendo
Write-Host "Cerrando proceso agent.py si existe..." -ForegroundColor Cyan
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -match "" -or $_.CommandLine -match "agent.py"
} | ForEach-Object { Stop-Process -Id $_.Id -Force }
Get-Process -Name "WindowsAgent*" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Hecho." -ForegroundColor Green
