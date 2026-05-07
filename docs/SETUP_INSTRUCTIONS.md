# Instrucciones de Setup — bot3-qlearning

## Estado actual (2026-05-06)

El proyecto esta completamente operativo y probado en produccion:
- bot3 corre en `localhost:8001`
- bot1 corre en `localhost:8000`
- Integracion confirmada: orden SPY ejecutada en Alpaca (live)

---

## Requisitos

- Python 3.10+
- bot1 (Trading-bot) corriendo en `localhost:8000` con el endpoint `/webhook/bot3`
- Archivo `.env` configurado (ver abajo)

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
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret        # el BOT3_WEBHOOK_SECRET de bot1

# Modo de ejecucion
DRY_RUN=false       # false = envia ordenes reales a bot1/Alpaca
PORT=8001

# Secreto para alertas de TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123        # ponlo tambien en TradingView

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Verificar que todo funciona

```powershell
# 1. Bot3 health
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# 2. Estado Q-Learning
Invoke-WebRequest http://localhost:8001/qlearning/status | Select-Object -ExpandProperty Content

# 3. Test de señal manual
$headers = @{ "Content-Type" = "application/json"; "X-Webhook-Secret" = "mi_secreto_webhook_123" }
$body = Get-Content tests/fixtures/tv_envelope_buy.json -Raw
Invoke-WebRequest -Uri http://localhost:8001/webhook/tv -Method POST -Headers $headers -Body $body
```

Respuesta esperada:
```json
{
  "status": "executed",
  "order_id": "<uuid-real-de-alpaca>",
  "ql_action": "EXECUTE_FULL",
  "state": "trend_up|mid|bullish"
}
```

---

## Cambios que se hicieron en bot1

Para que bot1 acepte señales de bot3, se aplicaron estos cambios:

**`.env` de bot1:**
```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

**`core/bot_registry.py` de bot1:**
- `"bot3_qlearning"` añadido a `KNOWN_BOTS`

**`bot.py` de bot1:**
- `bot3_decisions_path` → log en `data/bot3_decisions.jsonl`
- `_is_allowed_bot3_host()` → valida IP de origen (localhost only)
- `_log_bot3_decision()` → registra cada decision
- `_get_signal_source()` → detecta strategy_id que empiece por "bot3"
- `POST /webhook/bot3` → endpoint dedicado con secreto propio

---

## Tests

```bash
pytest tests/ -v
# 6/6 pasan
```
