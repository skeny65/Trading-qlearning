@echo off
setlocal enabledelayedexpansion
title Bot3 Q-Learning (:8001)

REM ============================================================
REM  Directorio base: carpeta donde esta este .bat
REM ============================================================
cd /d "%~dp0"

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
REM  Valores por defecto si .env no los tiene
REM ============================================================
if "%PORT%"==""              set PORT=8001
if "%DRY_RUN%"==""           set DRY_RUN=false
if "%QLEARNING_ENABLED%"=="" set QLEARNING_ENABLED=true

REM ============================================================
REM  Directorio de logs
REM ============================================================
if not exist "logs" mkdir logs

REM ============================================================
REM  Banner
REM ============================================================
cls
echo.
echo  ============================================================
echo   BOT3 Q-LEARNING  ^|  Trading Signal Agent
echo  ============================================================
echo.
echo   Directorio : %~dp0
echo   Puerto     : %PORT%
echo   DRY_RUN    : %DRY_RUN%
echo   Q-Learning : %QLEARNING_ENABLED%
echo   Bot1 URL   : %BOT1_WEBHOOK_URL%
echo.
echo   Endpoints utiles:
echo     POST  http://localhost:%PORT%/webhook/tv
echo     GET   http://localhost:%PORT%/health
echo     GET   http://localhost:%PORT%/qlearning/status
echo.
echo  ============================================================
echo.

REM ============================================================
REM  1. Verificar Python
REM ============================================================
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python no encontrado. Instala Python 3.10+ y agrega al PATH.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do echo        %%V
echo.

REM ============================================================
REM  2. Instalar / actualizar dependencias
REM ============================================================
echo [2/4] Instalando dependencias...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  ERROR: Fallo al instalar dependencias.
    echo  Ejecuta manualmente:  pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo        OK - dependencias al dia.
echo.

REM ============================================================
REM  3. Verificar conexion con bot1 (localhost)
REM ============================================================
echo [3/4] Verificando bot1 en localhost:8000...
powershell -Command "try { $r = Invoke-WebRequest http://localhost:8000/health -TimeoutSec 3 -UseBasicParsing; Write-Host '       OK - bot1 respondio:' $r.StatusCode } catch { Write-Host '       AVISO: bot1 no responde - bot3 arrancara igual' }"
echo.

REM ============================================================
REM  4. Arrancar ngrok en ventana separada (puerto 8001)
REM ============================================================
echo [4/4] Arrancando ngrok en puerto %PORT%...
start "ngrok Bot3" cmd /k "ngrok http --domain=shaft-goliath-shakable.ngrok-free.dev %PORT%"
echo        OK - ngrok arrancado en ventana separada.
echo.

REM ============================================================
REM  Loop de auto-restart 24/7
REM  Si uvicorn cae, espera 5 seg y vuelve a arrancar.
REM ============================================================
echo  ============================================================
echo   Arrancando bot3... (Ctrl+C para detener)
echo  ============================================================
echo.

:restart_loop
echo  [%time%] Iniciando uvicorn en puerto %PORT%...
echo.

python -X utf8 -m uvicorn bot3:app --host 0.0.0.0 --port %PORT% --log-level info

REM Si uvicorn termina, evaluar si fue manual o crash
set _exit=%errorlevel%

if %_exit% EQU 0 (
    echo.
    echo  [%time%] Bot3 detenido normalmente. Saliendo.
    goto :fin
)

echo.
echo  ============================================================
echo   [%time%] Bot3 termino con codigo %_exit%.
echo   Reiniciando en 5 segundos... (Ctrl+C para cancelar)
echo  ============================================================
echo.
timeout /t 5 /nobreak >nul

goto :restart_loop

:fin
echo.
echo  Bot3 detenido. Revisa los logs en la carpeta logs\
echo.
pause
endlocal
