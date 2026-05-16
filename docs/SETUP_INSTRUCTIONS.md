# Instrucciones de Setup - bot3 Multi-Strategy

## Estado actual (2026-05-16)

Sistema operativo con 10 estrategias independientes:
- **Estrategias 1 y 2:** flujo de 2 alertas (open + close desde TradingView)
- **Estrategias 3-10:** flujo de 1 alerta + Price Poller (detecta TP/SL via Binance)
- Excel por estrategia llenado automaticamente con WIN/LOSS
- bot1 es opcional: el bot aprende con o sin el

---

## Requisitos

- Python 3.10+
- Acceso a internet (Price Poller usa Binance API publica, sin key)
- Archivo `.env` configurado
- bot1 opcional (si quieres ejecutar en Alpaca)

---

## Arranque rapido

```bat
REM Doble clic:
start_bot3.bat
```

El bat hace todo automaticamente:
1. Verifica Python
2. Instala dependencias (`pip install -r requirements.txt`)
3. Verifica bot1 (aviso si no esta, no bloquea)
4. Abre ngrok en ventana separada
5. Arranca uvicorn en puerto 8001
6. Auto-restart si cae (loop 24/7)

---

## Configurar `.env`

```env
# Conexion con bot1 (opcional)
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret

# Modo
DRY_RUN=false
PORT=8001

# Secreto para alertas de TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## URLs de TradingView (produccion)

```
Estrategia 1 (apertura):  https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/1?secret=mi_secreto_webhook_123
Estrategia 1 (cierre):    https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/1?secret=mi_secreto_webhook_123
Estrategia 2 (apertura):  https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/2?secret=mi_secreto_webhook_123
Estrategia 2 (cierre):    https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/2?secret=mi_secreto_webhook_123
Estrategia 3:             https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/3?secret=mi_secreto_webhook_123
Estrategias 4-10:         https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/{id}?secret=mi_secreto_webhook_123
```

La misma URL sirve tanto para open como para close — el campo `signal_type` en el body es lo que distingue el tipo de alerta.

---

## Verificar que todo funciona

```powershell
# 1. Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# 2. Listar las 10 estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# 3. Test apertura estrategia 1
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price      = 91.57
            f1_sep     = 0.627
            f2_angle   = 0.906
            f3_d200    = 1.701
            d200_trend = "bajista"
            slope      = "up"
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
            price        = 91.30
            entry_price  = 91.57
            close_reason = "cross"
            pnl_pct      = -0.29
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body

# 5. Test apertura estrategia 2
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price          = 93.73
            sl             = 93.63
            tp             = 93.93
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
logs\1\trade_log.xlsx   <- estrategia 1 (Apuesta / TEMA 21-55)
logs\2\trade_log.xlsx   <- estrategia 2 (QLearning 5D)
logs\3\trade_log.xlsx   <- estrategia 3 (Tanque)
# etc.

# Diario de aprendizaje (actualizado tras cada trade cerrado)
Get-Content logs\1\INSIGHTS.md
Get-Content logs\2\INSIGHTS.md

# Via API
Invoke-WebRequest http://localhost:8001/api/strategy/1/journal | Select-Object -ExpandProperty Content
Invoke-WebRequest http://localhost:8001/api/strategy/2/journal | Select-Object -ExpandProperty Content
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
python scripts/learn_from_excel.py 2
```

El script lee columna `result` (WIN/LOSS) del Excel y dispara aprendizaje
para las filas que aun no tienen `learned_at`.

---

## Reiniciar y restaurar

```powershell
# Reiniciar bot3 (start_bot3.bat lo hace automaticamente)
taskkill /f /im python.exe

# Restaurar Q-Table de estrategia 1 desde backup
Copy-Item "data\strategies\1\backups\q_table_20260516_060000.json" `
          "data\strategies\1\q_table.json"

# Resetear Q-Table de una estrategia (empieza desde cero)
'{}' | Out-File data\strategies\1\q_table.json -Encoding utf8

# Borrar Excel para empezar de cero (bot lo recrea automaticamente)
Remove-Item logs\1\trade_log.xlsx
```

---

## Cambios necesarios en bot1 (si lo usas)

**`.env` de bot1:**
```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

**`core/bot_registry.py` de bot1:**
- Agregar `"bot3_1"`, `"bot3_2"`, ..., `"bot3_10"` a `KNOWN_BOTS`

Ver `docs/integration_bot1.md` para los detalles.
