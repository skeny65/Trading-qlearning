# API Reference - bot3 Multi-Strategy

Base URL: `http://localhost:8001`

---

## `GET /`

Health check rapido.

```json
{"status": "ok", "bot": "bot3-qlearning"}
```

---

## `GET /health`

Estado detallado del bot, todas las estrategias, y el Price Poller.

```json
{
  "status":        "ok",
  "dry_run":       false,
  "price_poller":  "running",
  "pending_count": 2,
  "strategies": ["apuesta", "qlearning", "tanque"]
}
```

---

## `POST /webhook/strategy/{id}`

Recibe alertas de TradingView y las procesa con el agente Q-Learning de la estrategia indicada.

**Estrategias disponibles:** `apuesta`, `qlearning`, `tanque`

**Headers requeridos:**
```
Content-Type:     application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

**Body:** ver `docs/webhook_format.md`

**Respuestas:**

| HTTP | status                | Significado                                              |
|------|-----------------------|----------------------------------------------------------|
| 200  | executed              | Q-Learning eligio EXECUTE_FULL o HALF, bot1 ejecuto      |
| 200  | executed_dry_run      | DRY_RUN=true, no se envio a bot1                         |
| 200  | skipped_by_qlearning  | Q-Learning decidio SKIP                                  |
| 200  | inverted_by_qlearning | Q-Learning ejecuto la operacion contraria                |
| 200  | rejected              | Agente pausado                                           |
| 200  | received_no_signal_tv | status != "pending", no se tomo accion                   |
| 400  | -                     | JSON invalido                                            |
| 401  | -                     | X-Webhook-Secret incorrecto                              |
| 403  | -                     | IP no permitida (si TV_ENFORCE_IP_WHITELIST=true)        |
| 404  | -                     | strategy_id no existe                                    |
| 422  | -                     | Campos faltantes o invalidos                             |

**Ejemplo de respuesta exitosa:**
```json
{
  "strategy_id":     "qlearning",
  "symbol":          "SOLUSDT",
  "original_action": "buy",
  "ql_action":       "EXECUTE_FULL",
  "state":           "trend_up|bullish|breakout|bull|extreme",
  "q_value":         0.0,
  "execute":         true,
  "side":            "buy",
  "size":            0.1,
  "status":          "executed",
  "order_id":        "759b9684-528d-47cc-b54a-98aa68003a5a",
  "dry_run":         false,
  "reason":          "[qlearning] Q-Learning: execute full",
  "timestamp":       "2026-05-06T21:17:39.517354+00:00"
}
```

---

## `GET /api/strategies`

Lista todas las estrategias registradas y su estado.

```json
{
  "strategies": [
    {"strategy_id": "apuesta",   "paused": false, "epsilon": 0.2000, "alpha": 0.1000, "qtable_states": 0},
    {"strategy_id": "qlearning", "paused": false, "epsilon": 0.2000, "alpha": 0.1000, "qtable_states": 3},
    {"strategy_id": "tanque",    "paused": false, "epsilon": 0.2000, "alpha": 0.1000, "qtable_states": 0}
  ]
}
```

---

## `GET /api/strategy/{id}/status`

Estado detallado del agente de una estrategia.

```powershell
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/status | Select-Object -ExpandProperty Content
```

```json
{
  "strategy_id":   "qlearning",
  "paused":        false,
  "epsilon":       0.2000,
  "alpha":         0.1000,
  "qtable_states": 3
}
```

---

## `POST /api/strategy/{id}/pause`  /  `POST /api/strategy/{id}/resume`

Pausa o reactiva el agente de una estrategia manualmente.

```powershell
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/pause  -Method POST
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/resume -Method POST
```

---

## `POST /api/strategy/{id}/update`

Aprendizaje manual: envia el resultado de una posicion cerrada.
Util si el Price Poller no detecto el cierre (activo OTC, crypto no en Binance, etc.).

Usar el `order_id` que devolvio bot3 al ejecutar la orden.

**Body:**
```json
{
  "order_id":              "759b9684-528d-47cc-b54a-98aa68003a5a",
  "pnl_pct":              0.5,
  "duration_min":         45.0,
  "account_drawdown_pct": -1.2,
  "r_multiple":           1.5,
  "next_state":           "range|neutral|pullback|neutral|weak"
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

---

## `GET /api/strategy/{id}/journal`

Resumen del diario de aprendizaje: estados bloqueados, mejores estados, ultimas conclusiones.

```powershell
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal | Select-Object -ExpandProperty Content
```

```json
{
  "strategy_id":    "qlearning",
  "total_updates":  47,
  "blocked_states": [
    {"state": "range|bearish|pullback|bear|weak", "action": "EXECUTE_FULL", "q": -0.42, "interp": "..."}
  ],
  "best_states": [
    {"state": "trend_up|bullish|breakout|bull|extreme", "action": "EXECUTE_FULL", "q": 0.38, "interp": "..."}
  ],
  "recent_conclusions": [
    {"ts": "2026-05-08T14:23:00Z", "state": "...", "action": "EXECUTE_FULL", "reward": 0.45, "conclusion": "...", "blocked": false, "good": true}
  ]
}
```

---

## `GET /api/strategy/{id}/journal/recent`

Ultimas 20 entradas del journal en crudo (JSONL parseado).

```powershell
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal/recent | Select-Object -ExpandProperty Content
```

---

## `GET /api/strategy/{id}/journal/report`

Regenera y retorna el contenido actual de `logs/{id}/INSIGHTS.md`.

```powershell
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal/report | Select-Object -ExpandProperty Content
```

---

## `GET /pending`

Decisiones pendientes de cierre de posicion (siendo monitoreadas por el Price Poller).

```powershell
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

---

## Endpoints legacy (siguen funcionando)

Estos endpoints del sistema original siguen disponibles para compatibilidad:

| Metodo | Endpoint             | Descripcion                                  |
|--------|----------------------|----------------------------------------------|
| POST   | /webhook/tv          | Webhook original (usa estrategia qlearning)  |
| GET    | /qlearning/status    | Estado del agente qlearning (alias)          |
| GET    | /qlearning/qtable    | Q-table del agente qlearning                 |
| POST   | /qlearning/update    | Aprendizaje manual para qlearning            |
| POST   | /qlearning/pause     | Pausar agente qlearning                      |
| POST   | /qlearning/resume    | Reanudar agente qlearning                    |
