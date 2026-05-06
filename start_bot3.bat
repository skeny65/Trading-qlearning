@echo off
setlocal enabledelayedexpansion
title Bot3 Q-Learning

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
if "%DRY_RUN%"==""           set DRY_RUN=true
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
echo   Modo       : %DRY_RUN%  (DRY_RUN)
echo   Q-Learning : %QLEARNING_ENABLED%
echo   Bot1 URL   : %BOT1_WEBHOOK_URL%
echo.
echo   Endpoints utiles:
echo     POST  http://localhost:%PORT%/webhook/tv
echo     GET   http://localhost:%PORT%/health
echo     GET   http://localhost:%PORT%/qlearning/status
echo     POST  http://localhost:%PORT%/qlearning/pause
echo     POST  http://localhost:%PORT%/qlearning/resume
echo     GET   http://localhost:%PORT%/pending
echo.
echo  ============================================================
echo.

REM ============================================================
REM  1. Verificar Python
REM ============================================================
echo [1/3] Verificando Python...
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
echo [2/3] Instalando dependencias (requirements.txt)...
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
REM  3. Verificar conexion con bot1
REM ============================================================
echo [3/3] Verificando bot1 en %BOT1_WEBHOOK_URL%...
python -X utf8 -c "
import urllib.request, sys
try:
    url = '%BOT1_WEBHOOK_URL%'.replace('/webhook/bot3', '/health')
    r = urllib.request.urlopen(url, timeout=3)
    print('       OK - bot1 respondio:', r.status)
except Exception as e:
    print('       AVISO: bot1 no responde -', e)
    print('       Bot3 arrancara igual. Las senales se guardaran en cola.')
" 2>nul
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
set _timestamp=%date:~6,4%-%date:~3,2%-%date:~0,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set _timestamp=%_timestamp: =0%
set _logfile=logs\bot3_%_timestamp%.log

echo  [%time%] Iniciando uvicorn... log: %_logfile%
echo.

python -X utf8 -m uvicorn bot3:app ^
    --host 0.0.0.0 ^
    --port %PORT% ^
    --log-level info ^
    --no-access-log ^
    2>&1 | tee "%_logfile%"

REM Si uvicorn termina (crash o ctrl+c), evaluar
set _exit=%errorlevel%

REM Ctrl+C devuelve errorlevel 0 o negativo en algunos casos
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
