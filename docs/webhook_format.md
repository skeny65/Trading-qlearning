# Webhook Format - bot3 Multi-Strategy

## Endpoint

```
POST /webhook/strategy/{id}
```

**URL de produccion:**
```
https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/1?secret=mi_secreto_webhook_123
```

**Header alternativo:**
```
Content-Type:     application/json
X-Webhook-Secret: <valor de TV_WEBHOOK_SECRET en .env>
```

---

## Estrategia 1 — TEMA 21/55 + DEMA 200 (flujo 2 alertas)

La estrategia 1 utiliza **2 alertas por operacion**: una al abrir y otra al cerrar.
El Pine Script gestiona la logica de entrada/salida; bot3 aprende del resultado.

### Alerta 1 — APERTURA (`signal_type: "open"`)

```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":         91.57,
      "f1_sep":        0.627,
      "f2_angle":      0.906,
      "f3_d200":       1.701,
      "anti_parallel": "libre",
      "d200_trend":    "bajista",
      "slope":         "up"
    }
  }
}
```

> Para VENTA corta: `"action": "sell"` y `"slope": "down"`

**Que hace bot3:**
1. Extrae `f1_sep`, `f2_angle`, `f3_d200` y los convierte al estado Q
2. Q-Learning decide: `EXECUTE_FULL`, `EXECUTE_HALF`, `SKIP` o `INVERT`
3. Si ejecuta → envia a bot1 + guarda estado/accion en `open_positions[(1, SOLUSDT)]`
4. Registra en Excel y decision_log

**Estado Q resultante (27 combinaciones):**

| Dimension | Niveles | Umbral |
|-----------|---------|--------|
| f1_level  | wide / mid / tight  | >=0.5% / >=0.2% / <0.2% |
| f2_level  | strong / mid / flat | >=0.5% / >=0.2% / <0.2% |
| f3_level  | far / mid / near    | >=1.0% / >=0.3% / <0.3% |

Ejemplo: `"wide|strong|far"` → entrada en tendencia fuerte, lejos de DEMA200.

---

### Alerta 2 — CIERRE (`signal_type: "close"`)

```json
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        91.30,
      "entry_price":  91.57,
      "close_reason": "cross",
      "pnl_pct":      -0.29
    }
  }
}
```

> Para cerrar corto: `"action": "close_sell"`
> `close_reason`: `"cross"` (cruce opuesto) o `"anti_parallel"` (filtro bloqueado)

**Que hace bot3:**
1. Bypass Q-Learning → el cierre **siempre** se ejecuta
2. Envia orden de cierre a bot1
3. Recupera el estado/accion de la apertura via `open_positions`
4. Calcula `reward` con `pnl_pct` y duracion
5. Actualiza Q-table **inmediatamente** (sin esperar al Price Poller)
6. Escribe `WIN`/`LOSS` en el Excel con `pnl_notes`

**Si pnl_pct no viene en el payload**, bot3 lo calcula:
```
pnl_pct = (close_price - entry_price) / entry_price * 100
```

---

## Estrategia 2 — QLearning 5D (243 estados, 1 alerta)

```json
{
  "status": "pending",
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
      "regime":         "trend_up",
      "momentum":       "bullish",
      "setup_type":     "breakout",
      "htf_bias":       "bull",
      "trend_strength": "extreme"
    }
  }
}
```

Estado 5D: `regime|momentum|setup_type|htf_bias|trend_strength`
El cierre lo detecta el **Price Poller** (API Binance cada 60s via sl/tp).

---

## Estrategia 3 — Tanque (27 estados, 1 alerta)

```json
{
  "status": "pending",
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
      "bar_count":      2,
      "pattern":        "inside_bar"
    }
  }
}
```

Estado 3D: `entry_strength|bar_zone|pattern`

---

## Estrategias 4–10 — Scaffold (27 estados, 1 alerta)

```json
{
  "status": "pending",
  "signal": {
    "symbol":     "SOLUSDT",
    "action":     "buy",
    "confidence": 0.75,
    "size":       0.1,
    "params": {
      "price": 93.73,
      "sl":    93.63,
      "tp":    93.93
    }
  }
}
```

Estado 3D: `price_zone|rr_level|hour_zone` (scaffold — personalizar en `strategies/eN/worker.py`).

---

## Reglas del envelope

- `status` debe ser `"pending"` (cualquier otro valor es ignorado)
- `signal_type` es opcional; si no viene, se asume `"open"` (compatible con estrategias 2-10)
- `signal.action` puede ser `"buy"`, `"sell"`, `"close_buy"`, `"close_sell"`
- `signal.size` es fraccion del portafolio (0.1 = 10%)

---

## Test manual desde PowerShell

### Apertura (estrategia 1):
```powershell
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    status = "pending"
    signal = @{
        symbol      = "SOLUSDT"
        action      = "buy"
        signal_type = "open"
        size        = 0.1
        params      = @{
            price        = 91.57
            f1_sep       = 0.627
            f2_angle     = 0.906
            f3_d200      = 1.701
            close_reason = "libre"
            d200_trend   = "bajista"
            slope        = "up"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8001/webhook/strategy/1?secret=mi_secreto_webhook_123" `
    -Method POST -Headers $headers -Body $body
```

### Cierre (estrategia 1):
```powershell
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
```

---

## Formato que bot3 envia a bot1 (`/webhook/bot3`)

### Apertura:
```json
{
  "status": "pending",
  "signal": {
    "strategy_id": "bot3_1",
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "confidence":  0.75,
    "size":        0.1,
    "params": {
      "ql_action": "EXECUTE_FULL",
      "ql_state":  "wide|strong|far",
      "q_value":   0.3842,
      "price":     91.57
    }
  }
}
```

### Cierre:
```json
{
  "status": "pending",
  "signal": {
    "strategy_id": "bot3_1",
    "symbol":      "SOLUSDT",
    "action":      "sell",
    "confidence":  1.0,
    "size":        0.1,
    "params": {
      "ql_action":    "CLOSE",
      "ql_state":     "wide|strong|far",
      "close_reason": "cross"
    }
  }
}
```
