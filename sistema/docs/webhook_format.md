# Webhook Format - bot3 Multi-Strategy

## Endpoint

```
POST /webhook/strategy/{id}
```

**URL de produccion (ngrok):**
```
https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/{id}?secret=mi_secreto_webhook_123
```

**Respuesta siempre:** `{"ok": true}` — TradingView no necesita nada mas.

---

## Estrategia 1 — SOLUSDT / Brecha de medias + D300 (2 alertas, LIVE)

### Apertura
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":           85.30,
      "sl":              85.17,
      "dist_brecha":     0.142,
      "pendiente_verde": 0.038,
      "cierre_brecha":   0.051,
      "d300_trend":      "alcista",
      "dist_d300":       1.203,
      "slope":           "up"
    }
  }
}
```
> Para corto: `"action": "sell"`

### Cierre
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        85.55,
      "entry_price":  85.30,
      "close_reason": "Cruce contrario",
      "pnl_pct":      0.29
    }
  }
}
```
> Para cerrar corto: `"action": "close_sell"`
> `close_reason`: `"Cruce contrario"` o `"Stop Loss"`

**Estado Q (27 combinaciones):**

| Dimension       | Niveles               | Campo            | Umbral                     |
|-----------------|-----------------------|------------------|----------------------------|
| brecha_level    | wide / mid / tight    | `dist_brecha`    | >=0.5% / >=0.2% / <0.2%   |
| pendiente_level | strong / mid / flat   | `pendiente_verde`| >=0.05% / >=0.02% / <0.02% |
| d300_level      | far / mid / near      | `dist_d300`      | >=1.0% / >=0.3% / <0.3%   |

---

## Estrategia 2 — SOLUSDT / QLearning 5D (2 alertas, LEARN_ONLY)

### Apertura
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":          93.73,
      "regime":         "trend_up",
      "momentum":       "bullish",
      "setup_type":     "breakout",
      "htf_bias":       "bull",
      "trend_strength": "extreme"
    }
  }
}
```

### Cierre
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        94.20,
      "entry_price":  93.73,
      "close_reason": "cross",
      "pnl_pct":      0.50
    }
  }
}
```

**Estado Q (243 combinaciones):** `regime|momentum|setup_type|htf_bias|trend_strength`

> Esta estrategia NO ejecuta en Binance. Solo aprende (LEARN_ONLY).

---

## Estrategia 3 — SOLUSDT / Tanque (2 alertas, LEARN_ONLY)

### Apertura
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":          93.73,
      "entry_strength": "strong",
      "bar_count":      2,
      "pattern":        "inside_bar"
    }
  }
}
```

### Cierre
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        94.10,
      "entry_price":  93.73,
      "close_reason": "cross",
      "pnl_pct":      0.41
    }
  }
}
```

**Estado Q (27 combinaciones):** `entry_strength|bar_zone|pattern`

> Esta estrategia NO ejecuta en Binance. Solo aprende (LEARN_ONLY).

---

## Estrategia 4 — ETHUSDT / EMA 9/21/200 (2 alertas, LIVE)

Soporta largos y cortos. 4 variantes de alerta.

### Apertura largo
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":    2845.5,
      "f1_sep":   0.123,
      "f2_angle": 0.087,
      "f3_d200":  1.452
    }
  }
}
```

### Apertura corto
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "sell",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":    2845.5,
      "f1_sep":   0.123,
      "f2_angle": 0.087,
      "f3_d200":  1.452
    }
  }
}
```

### Cierre largo
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        2820.0,
      "entry_price":  2845.5,
      "close_reason": "strategy_exit",
      "pnl_pct":      -0.9
    }
  }
}
```

### Cierre corto
```json
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "close_sell",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        2820.0,
      "entry_price":  2845.5,
      "close_reason": "strategy_exit",
      "pnl_pct":      0.9
    }
  }
}
```

**Estado Q (27 combinaciones):**

| Dimension | Niveles               | Umbral                   |
|-----------|-----------------------|--------------------------|
| f1_level  | wide / mid / tight   | >=0.5% / >=0.2% / <0.2% |
| f2_level  | strong / mid / flat  | >=0.5% / >=0.2% / <0.2% |
| f3_level  | far / mid / near     | >=1.0% / >=0.3% / <0.3% |

---

## Estrategias 5-10 — Scaffold (1 alerta, Price Poller)

```json
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "buy",
    "size":   0.1,
    "params": {
      "price": 93.73,
      "sl":    93.63,
      "tp":    93.93
    }
  }
}
```

El cierre lo detecta automaticamente el Price Poller via Binance API cada 60s.
No se requiere segunda alerta.

---

## Reglas generales

| Campo          | Regla                                                         |
|----------------|---------------------------------------------------------------|
| `status`       | Siempre `"pending"` — cualquier otro valor es ignorado        |
| `signal_type`  | `"open"` para abrir, `"close"` para cerrar                    |
| `action`       | `"buy"`, `"sell"`, `"close_buy"`, `"close_sell"`              |
| `pnl_pct`      | Puede ser negativo. Float, no string. `"pnl_pct": -1.78`      |
| `price`        | Float, no string. `"price": 2845.5` no `"price": "2845.5"`   |
| `size`         | Ignorado — el bot calcula qty desde el balance de Binance     |

---

## URLs por estrategia

| Estrategia | URL |
|------------|-----|
| 1 | `https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/1?secret=mi_secreto_webhook_123` |
| 2 | `https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/2?secret=mi_secreto_webhook_123` |
| 3 | `https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/3?secret=mi_secreto_webhook_123` |
| 4 | `https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/4?secret=mi_secreto_webhook_123` |
| 5-10 | `https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/{id}?secret=mi_secreto_webhook_123` |

---

## Test manual desde PowerShell

### Apertura estrategia 1 (SOLUSDT BUY):
```powershell
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{ price = 91.57; f1_sep = 0.627; f2_angle = 0.906; f3_d200 = 1.701 }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers @{"Content-Type"="application/json"} -Body $body
```

### Cierre estrategia 1:
```powershell
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "close_buy"
        signal_type = "close"
        size        = 0.1
        params      = @{ price = 91.30; entry_price = 91.57; close_reason = "cross"; pnl_pct = -0.29 }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers @{"Content-Type"="application/json"} -Body $body
```

### Apertura estrategia 4 (ETHUSDT SELL corto):
```powershell
$body = @{
    status = "pending"
    signal = @{
        symbol      = "ETHUSDT"
        action      = "sell"
        signal_type = "open"
        size        = 0.1
        params      = @{ price = 2845.5; f1_sep = 0.123; f2_angle = 0.087; f3_d200 = 1.452 }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/4?secret=mi_secreto_webhook_123" `
    -Method POST -Headers @{"Content-Type"="application/json"} -Body $body
```
