@echo off
setlocal enabledelayedexpansion
title BOT_EJECUTOR v2 (:8001)

REM ============================================================
REM  Directorio base -> sistema/
REM ============================================================
cd /d "%~dp0sistema"

REM ============================================================
REM  Leer .env (ignora comentarios y lineas vacias)
REM ============================================================
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "_line=%%A"
        if not "!_line:~0,1!"=="#" if not "%%A"=="" (
            set "%%A=%%B"
        )
    )
)

REM ============================================================
REM  Valores por defecto
REM ============================================================
if "%PORT%"==""    set PORT=8001
if "%DRY_RUN%"=="" set DRY_RUN=true

REM ============================================================
REM  Directorios necesarios
REM ============================================================
if not exist "logs" mkdir logs

REM ============================================================
REM  Banner
REM ============================================================
cls
echo.
echo  ============================================================
echo   BOT_EJECUTOR v2  ^|  Router de Ejecucion Binance Futures
echo  ============================================================
echo.
echo   Raiz    : %~dp0
echo   Sistema : %~dp0sistema
echo   Puerto  : %PORT%
echo   DRY_RUN : %DRY_RUN%
echo   Binance : Futuros USDT-M
echo.
echo   Carpetas: 1=TV ^| 2=TV ^| 3=TV ^| 4=TV ^| 5-8=Generico ^| 9=Grid ^| 10=Manager
echo.
echo   Emisores aceptados:
echo     TradingView ^-^> POST http://localhost:%PORT%/webhook/1   (carpetas 1-4)
echo     BOT_GRID    ^-^> POST http://localhost:%PORT%/webhook/9
echo     BOT_MANAGER ^-^> POST http://localhost:%PORT%/webhook/10
echo.
echo   Consultas:
echo     GET http://localhost:%PORT%/health
echo     GET http://localhost:%PORT%/api/folders
echo     GET http://localhost:%PORT%/api/metrics
echo     GET http://localhost:%PORT%/pending
echo.
echo  ============================================================
echo.

REM ============================================================
REM  1. Verificar Python 3.10+
REM ============================================================
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python no encontrado en PATH.
    echo  Descarga: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do echo        %%V ok
echo.

REM ============================================================
REM  2. Instalar / actualizar dependencias
REM ============================================================
echo [2/4] Instalando dependencias (requirements.txt)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  ERROR: Fallo pip install. Intenta manualmente:
    echo    pip install -r sistema\requirements.txt
    echo.
    pause
    exit /b 1
)
echo        OK - dependencias instaladas.
echo.

REM ============================================================
REM  3. Verificar conectividad con Binance
REM ============================================================
echo [3/4] Verificando conectividad con Binance...
powershell -Command "try { Invoke-WebRequest https://api.binance.com/api/v3/ping -TimeoutSec 5 -UseBasicParsing | Out-Null; Write-Host '       OK - Binance accesible' } catch { Write-Host '       AVISO: Binance no responde - verifica conexion/API keys' }"
echo.

REM ============================================================
REM  4. Arrancar ngrok en ventana separada
REM ============================================================
echo [4/4] Arrancando ngrok (puerto %PORT%)...
start "ngrok - BOT_EJECUTOR" cmd /k "ngrok http --domain=shaft-goliath-shakable.ngrok-free.dev %PORT%"
echo        OK - ngrok arrancando en ventana separada.
echo        URL publica: https://shaft-goliath-shakable.ngrok-free.dev/webhook/{id}
echo.

REM ============================================================
REM  Health Monitor (ventana separada, refresca cada 30s)
REM ============================================================
start "Health Monitor - BOT_EJECUTOR" powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0sistema\scripts\health_monitor.ps1" -Port %PORT%
echo        Health monitor abierto en ventana separada.
echo.

REM ============================================================
REM  Loop de auto-restart 24/7
REM  Si uvicorn cae por error, espera 5s y vuelve a arrancar.
REM  Ctrl+C detiene limpiamente.
REM ============================================================
echo  ============================================================
echo   Iniciando bot_ejecutor... (Ctrl+C para detener)
echo  ============================================================
echo.

:restart_loop
echo  [%time%] Arrancando uvicorn en 0.0.0.0:%PORT%...
echo.

python -X utf8 -m uvicorn bot3:app --host 0.0.0.0 --port %PORT% --log-level info

set _exit=%errorlevel%

if %_exit% EQU 0 (
    echo.
    echo  [%time%] Bot detenido normalmente. Adios.
    goto :fin
)

echo.
echo  ============================================================
echo   [%time%] Bot termino con error (codigo %_exit%).
echo   Reiniciando en 5 segundos... (Ctrl+C para cancelar)
echo  ============================================================
echo.
timeout /t 5 /nobreak >nul

goto :restart_loop

:fin
echo.
echo  Logs en: sistema\logs\
echo.
pause
endlocal
