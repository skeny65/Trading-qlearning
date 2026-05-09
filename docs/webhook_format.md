# Webhook Format - bot3 Multi-Strategy

## Endpoint principal: `/webhook/strategy/{id}`

**Header:**
```
Content-Type:     application/json
X-Webhook-Secret: <valor de TV_WEBHOOK_SECRET en .env>
```

---

## Formato para la estrategia `qlearning` (5D - 243 estados)

```json
{
  "timestamp": "2026-05-08T14:23:00Z",
  "status":    "pending",
  "processed": false,
  "source":    "tradingview",
  "signal": {
    "symbol":     "SOLUSDT",
    "action":     "buy",
    "confidence": 0.70,
    "size":       0.1,
    "params": {
      "price":          93.73,
      "sl":             93.63,
      "tp":             93.93,
      "atr":            0.066,
      "adx":            40.66,
      "rsi":            68.66,
      "regime":         "trend_up",
      "momentum":       "bullish",
      "setup_type":     "breakout",
      "htf_bias":       "bull",
      "trend_strength": "extreme"
    }
  }
}
```

**Campos `params` para qlearning:**

| Campo          | Tipo  | Valores validos                             | Usado para          |
|----------------|-------|---------------------------------------------|---------------------|
| price          | float | precio de entrada                           | entry_price en poller|
| sl             | float | stop loss                                   | cierre automatico   |
| tp             | float | take profit                                 | cierre automatico   |
| atr            | float | ATR en el momento de la senal               | contexto            |
| adx            | float | ADX (0-100)                                 | trend_strength fallback |
| rsi            | float | RSI (0-100)                                 | contexto            |
| regime         | str   | trend_up \| trend_down \| range             | estado 5D           |
| momentum       | str   | bullish \| bearish \| neutral               | estado 5D           |
| setup_type     | str   | breakout \| pullback \| trend               | estado 5D           |
| htf_bias       | str   | bull \| bear \| neutral (o bullish/bearish) | estado 5D           |
| trend_strength | str   | extreme \| strong \| moderate \| weak       | estado 5D           |

**IMPORTANTE:** `sl` y `tp` son necesarios para que el Price Poller detecte el cierre
automaticamente y el agente aprenda. Sin ellos, el aprendizaje debera hacerse manual.

---

## Formato para la estrategia `apuesta` (3D - 36 estados)

```json
{
  "timestamp": "2026-05-08T14:23:00Z",
  "status":    "pending",
  "source":    "tradingview",
  "signal": {
    "symbol":     "SOLUSDT",
    "action":     "buy",
    "confidence": 0.75,
    "size":       0.1,
    "params": {
      "price": 93.73,
      "sl":    93.63,
      "tp":    93.93,
      "atr":   0.066
    }
  }
}
```

La estrategia `apuesta` deriva el estado de: precio relativo al dia (price_zone),
ratio R:R calculado de sl/tp (rr_level), y hora UTC de la senal (hour_zone).

---

## Formato para la estrategia `tanque` (3D - 27 estados)

```json
{
  "timestamp": "2026-05-08T14:23:00Z",
  "status":    "pending",
  "source":    "tradingview",
  "signal": {
    "symbol":     "SOLUSDT",
    "action":     "buy",
    "confidence": 0.80,
    "size":       0.1,
    "params": {
      "price":          93.73,
      "sl":             93.63,
      "tp":             93.93,
      "entry_strength": "strong",
      "pattern":        "engulfing"
    }
  }
}
```

---

## Reglas del envelope

- El bot ignora silenciosamente envelopes con `status != "pending"`
- `signal.action` puede ser `"buy"` o `"sell"` (minusculas)
- `signal.size` es el size relativo (0.1 = 10% del portafolio en bot1)
- El campo `strategy_id` dentro de `signal` es opcional; la URL ya identifica la estrategia

---

## Test manual desde PowerShell

```powershell
$headers = @{
    "Content-Type"     = "application/json"
    "X-Webhook-Secret" = "mi_secreto_webhook_123"
}
$body = @{
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    status    = "pending"
    source    = "tradingview"
    signal    = @{
        symbol     = "SOLUSDT"
        action     = "buy"
        confidence = 0.70
        size       = 0.1
        params     = @{
            price          = 93.73
            sl             = 93.63
            tp             = 93.93
            atr            = 0.066
            adx            = 40.66
            regime         = "trend_up"
            momentum       = "bullish"
            setup_type     = "breakout"
            htf_bias       = "bull"
            trend_strength = "extreme"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri http://localhost:8001/webhook/strategy/qlearning `
    -Method POST -Headers $headers -Body $body
```

---

## Formato que bot3 envia a bot1 (`/webhook/bot3`)

Cuando Q-Learning decide ejecutar, bot3 construye este payload y lo envia a bot1:

```json
{
  "timestamp": "2026-05-08T14:23:00Z",
  "status":    "pending",
  "signal": {
    "strategy_id": "bot3_qlearning",
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "confidence":  0.70,
    "size":        0.1,
    "params": {
      "source":          "bot3_qlearning_agent",
      "strategy":        "qlearning",
      "ql_action":       "EXECUTE_FULL",
      "ql_state":        "trend_up|bullish|breakout|bull|extreme",
      "q_value":         0.3842,
      "price":           93.73,
      "sl":              93.63,
      "tp":              93.93,
      "atr":             0.066,
      "regime":          "trend_up",
      "momentum":        "bullish"
    }
  }
}
```

Header: `X-Webhook-Secret: <BOT1_WEBHOOK_SECRET>`
