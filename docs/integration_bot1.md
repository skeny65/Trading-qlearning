# Integracion con Bot1 — bot3-qlearning

## Estado: OPERATIVO (probado 2026-05-06)

Primera ejecucion real confirmada:
- Señal SPY BUY enviada desde bot3
- bot1 ejecuto la orden en Alpaca (live trading)
- `order_id: 759b9684-528d-47cc-b54a-98aa68003a5a`

---

## Arquitectura de la integracion

```
bot3 (localhost:8001)
        |
        |  POST http://127.0.0.1:8000/webhook/bot3
        |  Header: X-Webhook-Secret: <BOT3_WEBHOOK_SECRET>
        |  Body: payload JSON (ver formato abajo)
        v
bot1 (localhost:8000)
        |
        |  Ejecuta en Alpaca (live o paper)
        v
   {"status": "executed", "order_id": "uuid"}
```

La conexion es local (misma maquina) — latencia < 1ms.

---

## Cambios aplicados en bot1

### 1. `.env` de bot1

```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

### 2. `core/bot_registry.py`

`"bot3_qlearning"` añadido a `KNOWN_BOTS`.

### 3. `bot.py`

Funciones nuevas:
- `bot3_decisions_path` → log en `data/bot3_decisions.jsonl`
- `_is_allowed_bot3_host(request)` → valida que la peticion venga de localhost
- `_log_bot3_decision(entry)` → registra cada decision en JSONL
- `_get_signal_source(signal)` → detecta strategy_id que empiece por `"bot3"`

Endpoint nuevo:
```
POST /webhook/bot3
Header: X-Webhook-Secret: <BOT3_WEBHOOK_SECRET>
```

Flujo interno en bot1 para este endpoint:
1. Valida secreto (`BOT3_WEBHOOK_SECRET`) → 401 si falla
2. Valida IP origen (localhost only) → 403 si falla
3. Si `status != "pending"` → `{"status": "received_no_signal"}`
4. Si bot pausado → `{"status": "rejected", "reason": "..."}`
5. Ejecuta orden en Alpaca
6. Loguea en `data/bot3_decisions.jsonl`
7. Retorna `{"status": "executed", "order_id": "uuid"}`

---

## Payload que bot3 envia a bot1

```json
{
  "timestamp": "2026-05-06T21:17:39Z",
  "status": "pending",
  "signal": {
    "strategy_id": "bot3_qlearning",
    "symbol":      "SPY",
    "action":      "buy",
    "confidence":  0.75,
    "size":        0.1,
    "params": {
      "source":     "bot3_qlearning_agent",
      "ql_action":  "EXECUTE_FULL",
      "ql_state":   "trend_up|mid|bullish",
      "q_value":    0.0,
      "regime":     "trend_up",
      "volatility": "mid",
      "momentum":   "bullish",
      "price":      512.30,
      "sl":         510.20,
      "tp":         516.50,
      "atr":        1.45
    }
  }
}
```

---

## Respuestas que bot1 devuelve

| status                | Significado                                  | Accion en bot3              |
|-----------------------|----------------------------------------------|-----------------------------|
| `executed`            | Orden ejecutada en Alpaca                    | Log + Telegram + pending_q  |
| `rejected`            | Bot1 rechazo (pausado, limites, etc.)        | Log + Telegram              |
| `received_no_signal`  | Confirmacion de no_signal                    | Log                         |
| `failed`              | Fallo de red (no llego a bot1)               | state/pending_signals.json  |
| `dry_run`             | DRY_RUN=true en bot3 (no se envio nada)      | Log local                   |

---

## Retry automatico

Al arrancar bot3, `webhook_client.retry_pending()` reintenta todas las señales
en `state/pending_signals.json` que quedaron sin enviar en sesiones anteriores.

---

## Variables de entorno de bot3

```env
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret
```

> `BOT1_WEBHOOK_SECRET` debe coincidir exactamente con `BOT3_WEBHOOK_SECRET` en bot1.
