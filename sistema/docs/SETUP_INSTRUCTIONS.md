# Instrucciones de Setup - bot3 Multi-Strategy

## Estado actual (2026-05-27)

Sistema operativo con 10 estrategias independientes:
- **Estrategias 1 y 4:** LIVE — ejecutan ordenes reales en Binance Futures (flujo 2 alertas, SIN SL/TP en Binance)
- **Estrategias 2 y 3:** LEARN ONLY — reciben senales y aprenden sin ejecutar en Binance (flujo 2 alertas)
- **Estrategias 5-10:** LIVE — 1 alerta + Price Poller detecta TP/SL via Binance cada 60s (CON SL/TP en Binance)
- Excel por estrategia llenado automaticamente con WIN/LOSS y pnl_pct al cierre
- Ejecucion directa en Binance Futures (sin intermediarios)
- Balance en tiempo real: 95% del disponible usado por trade para evitar errores de margen

---

## Requisitos

- Python 3.10+
- Cuenta Binance con permisos de Futuros habilitados
- API Key de Binance con permisos de Futuros
- Archivo `.env` configurado
- ngrok (para recibir webhooks de TradingView)

---

## Arranque rapido

```bat
REM Doble clic:
start_bot3.bat
```

El bat hace todo automaticamente:
1. Verifica Python
2. Instala dependencias (`pip install -r requirements.txt`)
3. Verifica conectividad con Binance API
4. Abre ngrok en ventana separada
5. Arranca uvicorn en puerto 8001
6. Auto-restart si cae (loop 24/7)

---

## Configurar `.env`

```env
# Binance Futures (requerido)
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_API_SECRET=tu_api_secret_aqui
BINANCE_TESTNET=false
BINANCE_LEVERAGE=25
BINANCE_MAX_MARGIN_PCT=0.95

# Servidor
PORT=8001
DRY_RUN=false

# TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123
TV_ENFORCE_IP_WHITELIST=false

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Q-Learning
QLEARNING_ENABLED=true
QLEARNING_ALPHA_INITIAL=0.10
QLEARNING_GAMMA=0.90
QLEARNING_EPSILON_INITIAL=0.20
QLEARNING_EPSILON_MIN=0.02
QLEARNING_ALPHA_MIN=0.02
QLEARNING_DECAY_PER_TRADE=0.999
QLEARNING_BACKUP_INTERVAL_HOURS=6
QLEARNING_AUTO_PAUSE_WINDOW=20
QLEARNING_AUTO_PAUSE_WR_RATIO=0.7
```

---

## URLs de TradingView (produccion)

La misma URL sirve tanto para open como para close — el campo `signal_type` en el body es lo que distingue el tipo de alerta.

```
Estrategia 1 (SOLUSDT LIVE):    https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/1?secret=mi_secreto_webhook_123
Estrategia 2 (SOLUSDT LEARN):   https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/2?secret=mi_secreto_webhook_123
Estrategia 3 (SOLUSDT LEARN):   https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/3?secret=mi_secreto_webhook_123
Estrategia 4 (ETHUSDT LIVE):    https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/4?secret=mi_secreto_webhook_123
Estrategias 5-10:                https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/{id}?secret=mi_secreto_webhook_123
```

---

## Verificar que todo funciona

```powershell
# 1. Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# 2. Listar las 10 estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# 3. Test apertura estrategia 1 (SOLUSDT LIVE)
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price           = 85.30
            sl              = 85.17
            dist_brecha     = 0.627
            pendiente_verde = 0.906
            cierre_brecha   = 0.051
            d300_trend      = "alcista"
            dist_d300       = 1.203
            slope           = "up"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body

# 4. Test cierre estrategia 1
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "close_buy"
        signal_type = "close"
        size        = 0.1
        params      = @{
            price        = 85.55
            entry_price  = 85.30
            close_reason = "Cruce contrario"
            pnl_pct      = 0.29
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body

# 5. Test apertura estrategia 4 (ETHUSDT LIVE)
$body = @{
    status = "pending"
    signal = @{
        symbol      = "ETHUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price    = 3200.00
            f1_sep   = 0.55
            f2_angle = 0.70
            f3_d200  = 1.20
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/4?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body

# 6. Test apertura estrategia 2 (SOLUSDT LEARN ONLY — no ejecuta en Binance)
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price          = 93.73
            regime         = "trend_up"
            momentum       = "bullish"
            setup_type     = "breakout"
            htf_bias       = "bull"
            trend_strength = "extreme"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/2?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body
```

---

## Ver resultados

```powershell
# Excel de cada estrategia (llenado automaticamente)
logs\1\trade_log.xlsx   <- estrategia 1 (SOLUSDT / Brecha de medias + D300 — LIVE)
logs\2\trade_log.xlsx   <- estrategia 2 (SOLUSDT / QLearning 5D — LEARN ONLY)
logs\3\trade_log.xlsx   <- estrategia 3 (SOLUSDT / Tanque — LEARN ONLY)
logs\4\trade_log.xlsx   <- estrategia 4 (ETHUSDT / EMA 9-21-200 — LIVE)
# etc.

# Diario de aprendizaje (actualizado tras cada trade cerrado)
Get-Content logs\1\INSIGHTS.md
Get-Content logs\4\INSIGHTS.md

# Via API
Invoke-WebRequest http://localhost:8001/api/strategy/1/journal | Select-Object -ExpandProperty Content
Invoke-WebRequest http://localhost:8001/api/strategy/4/journal | Select-Object -ExpandProperty Content

# Posiciones activas (estrategias 5-10 monitoreadas por Price Poller)
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

---

## Aprendizaje manual (si necesitas corregir resultados)

```powershell
# Ver que se procesaria sin hacer nada
python scripts/learn_from_excel.py --dry-run

# Procesar todas las estrategias
python scripts/learn_from_excel.py

# Solo una estrategia
python scripts/learn_from_excel.py 1
python scripts/learn_from_excel.py 4
```

El script lee columna `result` (WIN/LOSS) del Excel y dispara aprendizaje
para las filas que aun no tienen `learned_at`.

---

## Reiniciar y restaurar

```powershell
# Reiniciar bot3 (start_bot3.bat lo hace automaticamente)
taskkill /f /im python.exe

# Restaurar Q-Table de estrategia 1 desde backup
Copy-Item "data\strategies\1\backups\q_table_20260518_060000.json" `
          "data\strategies\1\q_table.json"

# Resetear Q-Table de una estrategia (empieza desde cero)
'{}' | Out-File data\strategies\1\q_table.json -Encoding utf8

# Borrar Excel para empezar de cero (bot lo recrea automaticamente)
Remove-Item logs\1\trade_log.xlsx
```

---

## Configuracion de Binance

La API Key debe tener habilitados los permisos de **Futuros** (Futures Trading).
Sin este permiso, las ordenes fallaran con error de autorizacion.

Con `BINANCE_TESTNET=true` el bot usa la testnet de Binance Futures para pruebas
sin dinero real. Requiere una API Key separada generada en testnet.futures.binance.com.
