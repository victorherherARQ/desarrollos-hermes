@echo off
REM ============================================================
REM run.bat - arranca el agente en una ventana de consola
REM ============================================================
setlocal

cd /d "%~dp0"

REM Buscar Python: py launcher -> python -> python3
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python 3.8+ no encontrado. Instala desde python.org
        pause
        exit /b 1
    )
)

echo Iniciando Windows Agent...
%PY% agent.py

endlocal
