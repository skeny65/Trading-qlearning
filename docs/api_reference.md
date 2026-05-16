# API Reference - bot3 Multi-Strategy

Base URL: `http://localhost:8001`

---

## `GET /health`

Estado completo del sistema.

```json
{
  "status":        "ok",
  "dry_run":       false,
  "price_poller":  {"running": true, "poll_interval_sec": 60, "monitored_trades": 1},
  "pending_count": 1,
  "strategies":    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
}
```

---

## `POST /webhook/strategy/{id}`

Recibe alertas de TradingView. `{id}` puede ser `1` al `10`.

**URL de produccion:**
```
https://shaft-goliath-shakable.ngrok-free.dev/webhook/strategy/{id}?secret=mi_secreto_webhook_123
```

**Headers:**
```
Content-Type:     application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>   (alternativa al query param ?secret=)
```

### Alerta de apertura (`signal_type: "open"`)

El bot pasa la señal por Q-Learning y decide si ejecutar.

**Respuestas:**

| HTTP | status               | Descripcion                                         |
|------|----------------------|-----------------------------------------------------|
| 200  | queued               | Q-Learning decidio ejecutar, enviando a bot1        |
| 200  | skipped_by_qlearning | Q-Learning decidio SKIP                             |
| 200  | received_no_signal   | status != "pending", sin accion                     |
| 401  | -                    | Secret incorrecto                                   |
| 404  | -                    | strategy_id no existe                               |

**Respuesta cuando ejecuta:**
```json
{
  "strategy":        "1",
  "ticker":          "SOLUSDT",
  "original_action": "buy",
  "ql_action":       "EXECUTE_FULL",
  "state":           "wide|strong|far",
  "q_value":         0.3842,
  "execute":         true,
  "side":            "buy",
  "size":            0.1,
  "status":          "queued",
  "event_id":        "20260516_142300123456",
  "dry_run":         false,
  "timestamp":       "2026-05-16T14:23:00.000000+00:00"
}
```

### Alerta de cierre (`signal_type: "close"`) — estrategias 1 y 2

El bot cierra la posicion inmediatamente y actualiza Q-table al instante.

**Respuestas:**

| HTTP | status                  | Descripcion                                            |
|------|-------------------------|--------------------------------------------------------|
| 200  | close_queued            | Cierre enviado a bot1, Q-table y Excel actualizados    |
| 200  | close_no_open_tracked   | No habia apertura rastreada (bot reiniciado)           |

**Respuesta:**
```json
{
  "strategy":    "1",
  "symbol":      "SOLUSDT",
  "signal_type": "close",
  "action":      "close_buy",
  "close_reason": "cross",
  "pnl_pct":     -0.29,
  "open_found":  true,
  "status":      "close_queued",
  "timestamp":   "2026-05-16T14:55:00.000000+00:00"
}
```

---

## `GET /api/strategies`

Lista todas las estrategias con su estado actual.

```json
{
  "strategies": {
    "1":  {"strategy_id": "1",  "paused": false, "epsilon": 0.2000, "qtable_states": 5},
    "2":  {"strategy_id": "2",  "paused": false, "epsilon": 0.1980, "qtable_states": 12},
    "3":  {"strategy_id": "3",  "paused": false, "epsilon": 0.2000, "qtable_states": 0},
    "4":  {"strategy_id": "4",  "paused": false, "epsilon": 0.2000, "qtable_states": 0},
    ...
    "10": {"strategy_id": "10", "paused": false, "epsilon": 0.2000, "qtable_states": 0}
  },
  "count": 10
}
```

---

## `GET /api/strategy/{id}/status`

Estado del agente de una estrategia.

```json
{
  "strategy_id":   "2",
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
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/pause  -Method POST
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/2/resume -Method POST
```

---

## `POST /api/strategy/{id}/update`

Aprendizaje manual (para estrategias 3-10 o correcciones en 1-2).

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
  "order_id":    "20260516_142300123456",
  "pnl_pct":     1.45,
  "duration_min": 47.0,
  "state":       "wide|strong|far",
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
  "strategy_id":    "2",
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

Posiciones siendo monitoreadas por el Price Poller (estrategias 3-10).
Las estrategias 1 y 2 aprenden por alerta de cierre, no aparecen aqui tras el cierre.

```json
{
  "pending": {
    "20260516_142300123456": {
      "symbol": "SOLUSDT", "side": "buy",
      "entry_price": 93.73, "sl": 93.63, "tp": 93.93,
      "state": "trend_up|bullish|breakout|bull|extreme",
      "strategy_id": "2", "bot1_status": "executed"
    }
  },
  "count": 1
}
```

---

## Endpoints legacy (compatibilidad con flujo original)

| Metodo | Endpoint          | Descripcion                          |
|--------|-------------------|--------------------------------------|
| POST   | /webhook/tv       | Mismo que /webhook/strategy/2        |
| GET    | /qlearning/status | Alias de /api/strategy/2/status      |
| POST   | /qlearning/update | Alias de /api/strategy/2/update      |
| POST   | /qlearning/pause  | Alias de /api/strategy/2/pause       |
| POST   | /qlearning/resume | Alias de /api/strategy/2/resume      |
