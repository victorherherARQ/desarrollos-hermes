# Busca el Python real (no el stub de Microsoft Store) en todas las rutas estandar
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== BUSCANDO PYTHON REAL ===" -ForegroundColor Cyan
Write-Host ""

# 1. Carpetas estandar de Python
$standardPaths = @(
    "$env:LOCALAPPDATA\Programs\Python",
    "$env:LOCALAPPDATA\Programs\Python\Python314",
    "$env:LOCALAPPDATA\Programs\Python\Python313",
    "$env:LOCALAPPDATA\Programs\Python\Python312",
    "$env:LOCALAPPDATA\Programs\Python\Python311",
    "$env:LOCALAPPDATA\Programs\Python\Python310",
    "C:\Python314",
    "C:\Python313",
    "C:\Python312",
    "C:\Program Files\Python314",
    "C:\Program Files\Python313",
    "C:\Program Files\Python312",
    "C:\ProgramData\Anaconda3",
    "C:\Users\Victor\miniconda3",
    "C:\Users\Victor\anaconda3"
)

foreach ($p in $standardPaths) {
    $exe = Join-Path $p "python.exe"
    if (Test-Path $exe) {
        Write-Host "  [OK] Encontrado: $exe" -ForegroundColor Green
        Write-Host ""
        Write-Host "Copia esta ruta exacta y pegala en el chat:" -ForegroundColor Yellow
        Write-Host "  >>> $exe <<<" -ForegroundColor Yellow
        exit 0
    }
}

# 2. Busqueda recursiva en LOCALAPPDATA
Write-Host "Buscando recursivamente en %LOCALAPPDATA%\Programs..." -ForegroundColor Yellow
Get-ChildItem "$env:LOCALAPPDATA\Programs" -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Encontrado: $($_.FullName)" -ForegroundColor Green
}

# 3. Busqueda en disco C: (tarda mas)
Write-Host ""
$buscar = Read-Host "Buscar en todo C:\? (puede tardar 1-2 min) [s/N]"
if ($buscar -eq "s" -or $buscar -eq "S") {
    Write-Host "Buscando python.exe en C:\..." -ForegroundColor Yellow
    Get-ChildItem "C:\" -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue -Force | ForEach-Object {
        Write-Host "  $($_.FullName)"
    }
}

Write-Host ""
Write-Host "=== FIN ===" -ForegroundColor Cyan
