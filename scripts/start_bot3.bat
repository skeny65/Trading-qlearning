@echo off
REM start_bot3.bat - Arranca Bot3 Q-Learning (patron bot2: start_agente01.bat)
title Bot3 Q-Learning

echo.
echo ============================================================
echo   Bot3 Q-Learning - Trading Signal Agent
echo ============================================================
echo.

REM Cargar variables de entorno desde .env si existe
if exist .env (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%a"=="" (
            set "line=%%a"
            if not "!line:~0,1!"=="#" set %%a=%%b
        )
    )
)

echo   DRY_RUN      : %DRY_RUN%
echo   Q-LEARNING   : %QLEARNING_ENABLED%
echo   PORT         : %PORT%
echo   WEBHOOK URL  : %BOT1_WEBHOOK_URL%
echo.
echo   Endpoints:
echo     POST http://localhost:8001/webhook/tv       TradingView alertas
echo     GET  http://localhost:8001/health           Estado del bot
echo     GET  http://localhost:8001/qlearning/status Agente Q-Learning
echo     GET  http://localhost:8001/pending          Decisiones pendientes
echo.
echo ============================================================
echo.

python bot3.py

pause
