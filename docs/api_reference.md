# API Reference - bot3 Multi-Strategy

Base URL: `http://localhost:8001`

---

## `GET /health`

Estado completo del sistema.

```json
{
  "status":        "ok",
  "dry_run":       false,
  "price_poller":  {"running": true, "poll_interval_sec": 60, "monitored_trades": 2},
  "pending_count": 2,
  "strategies":    ["apuesta", "qlearning", "tanque"]
}
```

---

## `POST /webhook/strategy/{id}`

Recibe alertas de TradingView. Estrategias: `apuesta`, `qlearning`, `tanque`.

**Headers:**
```
Content-Type:     application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

**Respuestas:**

| HTTP | status                | Descripcion                                         |
|------|-----------------------|-----------------------------------------------------|
| 200  | queued                | Bot decidio ejecutar, enviando a bot1 en background |
| 200  | skipped_by_qlearning  | Q-Learning decidio SKIP                             |
| 200  | received_no_signal    | status != "pending", sin accion                     |
| 401  | -                     | X-Webhook-Secret incorrecto                         |
| 404  | -                     | strategy_id no existe                               |

**Respuesta cuando ejecuta:**
```json
{
  "strategy":        "qlearning",
  "ticker":          "SOLUSDT",
  "original_action": "buy",
  "ql_action":       "EXECUTE_FULL",
  "state":           "trend_up|bullish|breakout|bull|extreme",
  "q_value":         0.3842,
  "execute":         true,
  "side":            "buy",
  "size":            0.1,
  "status":          "queued",
  "event_id":        "20260509_142300123456",
  "dry_run":         false,
  "timestamp":       "2026-05-09T14:23:00.000000+00:00"
}
```

---

## `GET /api/strategies`

Lista todas las estrategias con su estado actual.

```json
{
  "strategies": {
    "apuesta":   {"strategy_id": "apuesta",   "paused": false, "epsilon": 0.2000, "qtable_states": 0},
    "qlearning": {"strategy_id": "qlearning", "paused": false, "epsilon": 0.1980, "qtable_states": 12},
    "tanque":    {"strategy_id": "tanque",    "paused": false, "epsilon": 0.2000, "qtable_states": 0}
  },
  "count": 3
}
```

---

## `GET /api/strategy/{id}/status`

Estado del agente de una estrategia.

```json
{
  "strategy_id":   "qlearning",
  "paused":        false,
  "epsilon":       0.1980,
  "alpha":         0.0990,
  "qtable_states": 12
}
```

---

## `POST /api/strategy/{id}/pause` / `POST /api/strategy/{id}/resume`

Pausa o reactiva el agente manualmente.

```powershell
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/pause  -Method POST
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/resume -Method POST
```

---

## `POST /api/strategy/{id}/update`

Aprendizaje manual. Dos modos:

**Modo 1 — por order_id** (si la posicion esta en pending_q_decisions):
```json
{
  "order_id":    "759b9684-528d-47cc-b54a-98aa68003a5a",
  "pnl_pct":     1.45,
  "duration_min": 47.0,
  "r_multiple":  2.34
}
```

**Modo 2 — directo con state y action** (funciona aunque bot3 se haya reiniciado):
```json
{
  "order_id":    "20260509_142300123456",
  "pnl_pct":     1.45,
  "duration_min": 47.0,
  "state":       "trend_up|bullish|breakout|bull|extreme",
  "action":      "EXECUTE_FULL"
}
```

**Campos:**

| Campo                | Tipo   | Requerido | Descripcion                                    |
|----------------------|--------|-----------|------------------------------------------------|
| order_id             | string | Si        | UUID de bot1 o event_id generado por bot3      |
| pnl_pct              | float  | Si        | PnL en % (positivo = ganancia)                 |
| duration_min         | float  | No        | Duracion en minutos                            |
| account_drawdown_pct | float  | No        | Drawdown de cuenta en % (negativo)             |
| r_multiple           | float  | No        | R-multiple del trade                           |
| next_state           | string | No        | Estado del mercado al cerrar                   |
| state                | string | No        | Estado al entrar (modo directo)                |
| action               | string | No        | Accion tomada (modo directo)                   |

---

## `GET /api/strategy/{id}/journal`

Resumen del diario de aprendizaje.

```json
{
  "strategy_id":    "qlearning",
  "total_updates":  47,
  "blocked_states": [{"state": "range|bearish|...", "action": "EXECUTE_FULL", "q": -0.42}],
  "best_states":    [{"state": "trend_up|bullish|...", "action": "EXECUTE_FULL", "q": 0.38}],
  "recent_conclusions": [...]
}
```

---

## `GET /api/strategy/{id}/journal/recent`

Ultimas 20 entradas del journal en crudo.

---

## `POST /api/strategy/{id}/journal/report`

Regenera y retorna el contenido de `logs/{id}/INSIGHTS.md`.

---

## `GET /pending`

Posiciones siendo monitoreadas por el Price Poller.

```json
{
  "pending": {
    "20260509_142300123456": {
      "symbol": "SOLUSDT", "side": "buy",
      "entry_price": 93.73, "sl": 93.63, "tp": 93.93,
      "state": "trend_up|bullish|breakout|bull|extreme",
      "strategy_id": "qlearning", "bot1_status": "executed"
    }
  },
  "count": 1
}
```

---

## Endpoints legacy (compatibilidad)

| Metodo | Endpoint          | Descripcion                        |
|--------|-------------------|------------------------------------|
| POST   | /webhook/tv       | Mismo que /webhook/strategy/qlearning |
| GET    | /qlearning/status | Alias de /api/strategy/qlearning/status |
| POST   | /qlearning/update | Alias de /api/strategy/qlearning/update |
| POST   | /qlearning/pause  | Alias de /api/strategy/qlearning/pause |
| POST   | /qlearning/resume | Alias de /api/strategy/qlearning/resume |
