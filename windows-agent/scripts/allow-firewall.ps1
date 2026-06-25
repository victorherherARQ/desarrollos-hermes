# ============================================================
# scripts/allow-firewall.ps1
# Abre el puerto 8765 en el firewall de Windows para que WSL/LAN
# puedan acceder al agente.
#
# Ejecutar como Administrador una sola vez.
# ============================================================
$port = 8765
$ruleName = "WindowsAgent-Monitor-Hardware"

Write-Host "[1/2] Comprobando regla existente..." -ForegroundColor Cyan
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Ya existe. Actualizando..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName $ruleName
}

Write-Host "[2/2] Creando regla de entrada en TCP/$port..." -ForegroundColor Cyan
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
Write-Host "  Regla creada." -ForegroundColor Green
Write-Host ""
Write-Host "Para ver la regla: Get-NetFirewallRule -DisplayName '$ruleName'" -ForegroundColor Cyan
Write-Host "Para abrir el puerto manualmente: netsh advfirewall firewall add rule name=... dir=in action=allow protocol=TCP localport=$port" -ForegroundColor Cyan
