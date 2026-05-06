# Webhook Format

## Formato TradingView (`/webhook/tv`)

El envelope sigue la misma filosofia que el envelope de Claude Routines.

**Header:**
```
X-Webhook-Secret: <valor de TV_WEBHOOK_SECRET en .env>
```

**Body:**
```json
{
  "timestamp": "2026-05-03T14:30:00Z",
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
