# Instrucciones de Setup - bot3 Multi-Strategy

## Estado actual (2026-05-08)

El proyecto esta completamente operativo:
- bot3 corre en `localhost:8001`
- bot1 corre en `localhost:8000`
- 3 estrategias independientes: `apuesta`, `qlearning`, `tanque`
- Price Poller: detecta TP/SL automaticamente via Binance API
- Primera orden real ejecutada (SPY, Alpaca live, 2026-05-06)

---

## Requisitos

- Python 3.10+
- bot1 (Trading-bot) corriendo en `localhost:8000` con el endpoint `/webhook/bot3`
- Archivo `.env` configurado (ver abajo)
- Acceso a internet (para Price Poller -> Binance API publica)

---

## Arranque rapido

```bat
REM Doble clic en la raiz del proyecto:
start_bot3.bat
```

El bat hace todo automaticamente:
1. Verifica Python
2. Instala/actualiza dependencias (`pip install -r requirements.txt`)
3. Verifica conectividad con bot1
4. Arranca uvicorn en puerto 8001
5. Si cae, reinicia solo en 5 segundos (loop 24/7)

---

## Configurar `.env`

Copia `.env.example` a `.env` y edita estos valores:

```env
# Conexion con bot1
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret

# Modo de ejecucion
DRY_RUN=false
PORT=8001

# Secreto para alertas de TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Verificar que todo funciona

```powershell
# 1. Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# 2. Listar estrategias y su estado
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# 3. Estado del agente qlearning
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/status | Select-Object -ExpandProperty Content

# 4. Test de senal manual para qlearning
$headers = @{ "Content-Type" = "application/json"; "X-Webhook-Secret" = "mi_secreto_webhook_123" }
$body = @{
    status = "pending"
    source = "tradingview"
    signal = @{
        symbol = "SOLUSDT"; action = "buy"; confidence = 0.7; size = 0.1
        params = @{
            price = 93.73; sl = 93.63; tp = 93.93; atr = 0.066; adx = 40.66
            regime = "trend_up"; momentum = "bullish"; setup_type = "breakout"
            htf_bias = "bull"; trend_strength = "extreme"
        }
    }
} | ConvertTo-Json -Depth 5
Invoke-WebRequest -Uri http://localhost:8001/webhook/strategy/qlearning -Method POST -Headers $headers -Body $body
```

Respuesta esperada:
```json
{
  "strategy_id": "qlearning",
  "status":      "executed",
  "ql_action":   "EXECUTE_FULL",
  "state":       "trend_up|bullish|breakout|bull|extreme"
}
```

---

## Configurar TradingView

En cada alerta de Pine Script:

- **URL:** `https://<tu-ngrok-id>.ngrok.io/webhook/strategy/qlearning`
  (cambia `qlearning` por `apuesta` o `tanque` segun la estrategia)
- **Header:** `X-Webhook-Secret: <TV_WEBHOOK_SECRET>`
- **Body:** JSON con el formato documentado en `docs/webhook_format.md`

Para que el aprendizaje sea automatico, el body debe incluir `sl` y `tp` en `params`.

---

## Ver el diario de aprendizaje

```powershell
# Archivo Markdown (siempre actualizado tras cada trade)
Get-Content logs\qlearning\INSIGHTS.md

# Via API
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal | Select-Object -ExpandProperty Content
```

---

## Cambios que se hicieron en bot1

Para que bot1 acepte senales de bot3, se aplicaron estos cambios:

**`.env` de bot1:**
```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

**`core/bot_registry.py` de bot1:**
- `"bot3_qlearning"` agregado a `KNOWN_BOTS`

Ver `docs/integration_bot1.md` para los detalles completos.

---

## Tests

```powershell
python -X utf8 -m pytest tests/ -v
```

---

## Estructura de datos en disco

Tras el primer uso, el sistema crea automaticamente:

```
data/strategies/
  apuesta/   qlearning/   tanque/    (q_table.json, stats, replay, backups)

state/
  apuesta/   qlearning/   tanque/    (decision_log.jsonl)

logs/
  apuesta/   qlearning/   tanque/    (INSIGHTS.md, learning_journal.jsonl, trade_log.xlsx, events/)
```

No es necesario crear estos directorios manualmente.

---

## Reiniciar y restaurar

```powershell
# Reiniciar bot3
taskkill /f /im python.exe
start_bot3.bat

# Restaurar Q-Table desde backup
Copy-Item "data\strategies\qlearning\backups\q_table_20260508_060000.json" `
          "data\strategies\qlearning\q_table.json"

# Resetear Q-Table de una estrategia
'{}' | Out-File data\strategies\qlearning\q_table.json -Encoding utf8
```
