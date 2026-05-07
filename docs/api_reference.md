# API Reference - bot3-qlearning

Base URL: `http://localhost:8001`

## Estado: OPERATIVO (probado 2026-05-06)

---

## `GET /`
Health check rapido.

```
HTTP 200
{"status": "ok", "bot": "bot3-qlearning"}
```

## `GET /health`
Estado detallado: dry_run, paused, epsilon, alpha, pending_decisions.

```json
{
  "status": "ok",
  "dry_run": false,
  "agent_paused": false,
  "epsilon": 0.20,
  "alpha": 0.10,
  "pending_decisions": 0
}
```

---

## `POST /webhook/tv`

Recibe alertas de TradingView y las procesa con el agente Q-Learning.

**Headers requeridos:**
```
Content-Type:     application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

**Body:** ver `docs/webhook_format.md`

**Respuestas:**

| HTTP | status                   | Significado                                       |
|------|--------------------------|---------------------------------------------------|
| 200  | executed                 | Q-Learning eligio EXECUTE_FULL o HALF, bot1 ejecuto |
| 200  | executed_dry_run         | DRY_RUN=true, no se envio a bot1                  |
| 200  | skipped_by_qlearning     | Q-Learning decidio SKIP                           |
| 200  | inverted_by_qlearning    | Q-Learning ejecuto la operacion contraria          |
| 200  | rejected                 | Agente pausado                                    |
| 200  | received_no_signal_tv    | status != "pending", no se tomo accion            |
| 400  | -                        | JSON invalido                                     |
| 401  | -                        | X-Webhook-Secret incorrecto                       |
| 403  | -                        | IP no permitida (si TV_ENFORCE_IP_WHITELIST=true) |
| 422  | -                        | Campos faltantes o invalidos en el envelope       |

**Ejemplo de respuesta exitosa (ejecutado en Alpaca):**
```json
{
  "ticker":          "SPY",
  "original_action": "buy",
  "ql_action":       "EXECUTE_FULL",
  "state":           "trend_up|mid|bullish",
  "q_value":         0.0,
  "execute":         true,
  "side":            "buy",
  "size":            0.1,
  "status":          "executed",
  "order_id":        "759b9684-528d-47cc-b54a-98aa68003a5a",
  "dry_run":         false,
  "reason":          "Q-Learning: execute full position",
  "timestamp":       "2026-05-06T21:17:39.517354+00:00"
}
```

---

## `GET /qlearning/status`

Resumen del agente: alpha, epsilon, paused, best/worst state-action, recent rewards.

```powershell
Invoke-WebRequest http://localhost:8001/qlearning/status | Select-Object -ExpandProperty Content
```

---

## `GET /qlearning/qtable`

Q-table completa en JSON.

```powershell
Invoke-WebRequest http://localhost:8001/qlearning/qtable | Select-Object -ExpandProperty Content
```

---

## `POST /qlearning/update`

Aplica aprendizaje hindsight cuando una posicion se cierra.
Usar el `order_id` que devolvio bot3 al ejecutar la orden.

**Body:**
```json
{
  "order_id":              "759b9684-528d-47cc-b54a-98aa68003a5a",
  "pnl_pct":              0.5,
  "duration_min":         45.0,
  "account_drawdown_pct": -1.2,
  "r_multiple":           1.5,
  "next_state":           "range|mid|neutral"
}
```

**Campos:**

| Campo                | Tipo   | Requerido | Descripcion                                  |
|----------------------|--------|-----------|----------------------------------------------|
| order_id             | string | Si        | UUID devuelto por bot3 al ejecutar la orden  |
| pnl_pct              | float  | Si        | PnL en % (positivo = ganancia)               |
| duration_min         | float  | Si        | Duracion de la operacion en minutos          |
| account_drawdown_pct | float  | No        | Drawdown de la cuenta en % (negativo)        |
| r_multiple           | float  | No        | R-multiple del trade (pnl / riesgo)          |
| next_state           | string | No        | Estado del mercado al cerrar la posicion     |

**Ejemplo PowerShell:**
```powershell
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    order_id              = "759b9684-528d-47cc-b54a-98aa68003a5a"
    pnl_pct              = 0.5
    duration_min         = 45.0
    account_drawdown_pct = -1.2
    r_multiple           = 1.5
    next_state           = "range|mid|neutral"
} | ConvertTo-Json

Invoke-WebRequest -Uri http://localhost:8001/qlearning/update `
    -Method POST -Headers $headers -Body $body
```

---

## `POST /qlearning/pause`  /  `POST /qlearning/resume`

Pausa o reactiva el agente manualmente.

```powershell
Invoke-WebRequest -Uri http://localhost:8001/qlearning/pause  -Method POST
Invoke-WebRequest -Uri http://localhost:8001/qlearning/resume -Method POST
```

---

## `GET /pending`

Decisiones pendientes de cierre de posicion (esperando `/qlearning/update`).

```powershell
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```
