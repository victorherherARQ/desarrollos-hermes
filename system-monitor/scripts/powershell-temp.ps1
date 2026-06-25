# =============================================================
# powershell-temp.ps1
# Lector de temperatura CPU/GPU desde el host Windows.
# Lo ejecutas en Windows (no en WSL). Publica la métrica por HTTP
# o la escribe en un fichero que un agente WSL puede leer.
# =============================================================
#
# Uso:
#   1. Abre PowerShell como Administrador en Windows
#   2. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   3. .\powershell-temp.ps1 -Port 8765
#
# Lee temperatura de:
#   - WMI MSAcpi_ThermalZoneTemperature (CPU genérico)
#   - Si tienes un vendor tool (HWInfo, Ryzen Controller, etc.),
#     exporta su CSV y esta función puede leerlo.
#
# Endpoint expuesto en http://<ip-windows>:8765/temp
# =============================================================

param(
    [int]$Port = 8765,
    [int]$IntervalSeconds = 5
)

# Listener HTTP simple
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$Port/")
$listener.Start()
Write-Host "Temperature exporter listening on http://+:$Port/temp" -ForegroundColor Green
Write-Host "Stop with Ctrl+C" -ForegroundColor Yellow

$running = $true
[Console]::TreatControlCAsInput = $false
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { $running = $false }

function Get-CpuTemp {
    try {
        $t = Get-WmiObject -Namespace "root/wmi" -Class "MSAcpi_ThermalZoneTemperature" -ErrorAction Stop
        foreach ($z in $t) {
            $c = ($z.CurrentTemperature - 2732) / 10.0
            if ($c -gt 0 -and $c -lt 110) { return [math]::Round($c, 1) }
        }
    } catch {}
    return $null
}

# Background poller que mantiene la última lectura en memoria
$script:lastTemp = $null
$script:lastTime = (Get-Date).AddMinutes(-10)
$timer = New-Object System.Timers.Timer
$timer.Interval = $IntervalSeconds * 1000
$timer.Add_Click({
    $t = Get-CpuTemp
    if ($t) { $script:lastTemp = $t; $script:lastTime = Get-Date }
})
$timer.Start()

while ($running) {
    try {
        $context = $listener.GetContext()
        $response = $context.Response
        $path = $context.Request.Url.AbsolutePath

        if ($path -eq "/temp") {
            $body = @{
                temp_c = $script:lastTemp
                ts = $script:lastTime.ToString("o")
                source = "WMI MSAcpi_ThermalZoneTemperature"
                wsl_note = "WSL2 cannot read this; needs this Windows-side exporter"
            } | ConvertTo-Json
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($body)
            $response.ContentType = "application/json"
        } elseif ($path -eq "/") {
            $body = "OK - use /temp"
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($body)
        } else {
            $response.StatusCode = 404
            $buffer = [System.Text.Encoding]::UTF8.GetBytes("not found")
        }

        $response.ContentLength64 = $buffer.Length
        $response.OutputStream.Write($buffer, 0, $buffer.Length)
        $response.OutputStream.Close()
    } catch {
        Write-Warning $_.Exception.Message
    }
}

$timer.Stop()
$listener.Stop()
