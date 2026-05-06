# Integracion con Bot1

## Patron identico a bot2

bot3 se integra con bot1 exactamente igual que bot2:

### Registro en bot1

bot3 debe estar registrado en bot1 con `strategy_id="bot3_qlearning"`.
En bot1, en el BotRegistry o estrategias registradas, debe existir:
```
strategy_id: "bot3_qlearning"
source:      "bot3_qlearning_agent"
webhook_path: /webhook/bot3
```

### Formato del webhook

POST `http://127.0.0.1:8000/webhook/bot3`
Header: `X-Webhook-Secret: <BOT1_WEBHOOK_SECRET>`

```json
{
  "timestamp": "2026-05-03T14:30:00Z",
  "status": "pending",
  "signal": {
    "strategy_id": "bot3_qlearning",
    "symbol": "SPY",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.10,
    "params": {
      "source":     "bot3_qlearning_agent",
      "ql_action":  "EXECUTE_FULL",
      "ql_state":   "trend_up|mid|bullish",
      "q_value":    0.1234,
      "regime":     "trend_up",
      "volatility": "mid",
      "momentum":   "bullish",
      "price":      520.50,
      "sl":         517.00,
      "tp":         527.00,
      "atr":        1.50
    }
  }
}
```

### Respuestas de bot1

| status              | Significado                              | Accion bot3         |
|---------------------|------------------------------------------|---------------------|
| `executed`          | bot1 ejecuto la orden en Alpaca          | Log + Telegram *   |
| `rejected`          | bot1 rechazo (bot pausado, etc.)         | Log + Telegram *   |
| `received_no_signal`| bot1 confirmo no_signal                  | Log                 |
| `failed`            | Fallo de red (no llego a bot1)           | pending_signals.json|
| `dry_run`           | DRY_RUN=true en bot3 (no se envio)       | Log local           |

### Retry automatico

Al arrancar bot3, `webhook_client.retry_pending()` reintenta todas las senales
en `state/pending_signals.json`. Identico al patron de bot2.

### Variables de entorno necesarias

```env
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=el_mismo_secreto_que_tiene_bot1
```
