# Webhook Format

## Formato TradingView (`/webhook/tv`)

**Header:**
```
Content-Type:     application/json
X-Webhook-Secret: <valor de TV_WEBHOOK_SECRET en .env>
```

**Body:**
```json
{
  "timestamp": "2026-05-06T21:17:00Z",
  "status": "pending",
  "processed": false,
  "source": "tradingview",
  "signal": {
    "strategy_id": "strategy_tv_qlearning",
    "symbol": "SPY",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.1,
    "params": {
      "price": 512.30,
      "sl": 510.20,
      "tp": 516.50,
      "atr": 1.45,
      "regime": "trend_up",
      "volatility": "mid",
      "momentum": "bullish"
    }
  }
}
```

**Campos `params` validos:**

| Campo      | Tipo  | Valores validos                             |
|------------|-------|---------------------------------------------|
| price      | float | precio de entrada                           |
| sl         | float | stop loss                                   |
| tp         | float | take profit                                 |
| atr        | float | ATR en el momento de la senal               |
| regime     | str   | trend_up \| trend_down \| range             |
| volatility | str   | low \| mid \| high                          |
| momentum   | str   | bullish \| bearish \| neutral               |

El bot ignora silenciosamente envelopes con `status != "pending"`.

---

## Test manual desde PowerShell

```powershell
$headers = @{
    "Content-Type"     = "application/json"
    "X-Webhook-Secret" = "mi_secreto_webhook_123"
}
$body = Get-Content tests\fixtures\tv_envelope_buy.json -Raw -Encoding UTF8
Invoke-WebRequest -Uri http://localhost:8001/webhook/tv -Method POST -Headers $headers -Body $body
```

## Test manual desde ngrok (produccion)

```
POST https://<tu-id>.ngrok.io/webhook/tv
Header: X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

---

## Formato que bot3 envia a bot1 (`/webhook/bot3`)

Cuando Q-Learning decide ejecutar, bot3 construye este payload y lo envia a bot1:

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

Header: `X-Webhook-Secret: <BOT1_WEBHOOK_SECRET>` (el mismo que `BOT3_WEBHOOK_SECRET` en bot1)
