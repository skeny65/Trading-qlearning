# API Reference - bot3 Multi-Strategy

Base URL: `http://localhost:8001`

---

## `GET /health`

Estado completo del sistema.

```json
{
  "status":        "ok",
  "dry_run":       false,
  "price_poller":  {"running": true, "poll_interval_sec": 60, "monitored_trades": 0},
  "pending_count": 0,
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

**Respuesta siempre:** `{"ok": true}` — 200 OK en todos los casos validos.

### Comportamiento por signal_type

| signal_type | Accion                                                             |
|-------------|---------------------------------------------------------------------|
| `"open"`    | Q-Learning decide → ejecuta en Binance (LIVE) o simula (LEARN_ONLY)|
| `"close"`   | Bypass Q → cierra en Binance → actualiza Q-table y Excel inmediato  |
| ausente     | Se asume `"open"` (compatible con estrategias 5-10)                |

### Codigos de error

| HTTP | Causa                              |
|------|------------------------------------|
| 400  | JSON invalido                      |
| 401  | Secret incorrecto                  |
| 404  | strategy_id no registrada          |
| 422  | Error al procesar la senal         |

---

## `GET /api/strategies`

Lista todas las estrategias con su estado actual.

```json
{
  "strategies": {
    "1":  {"strategy_id": "1",  "paused": false, "epsilon": 0.2000, "qtable_states": 5},
    "2":  {"strategy_id": "2",  "paused": false, "epsilon": 0.1980, "qtable_states": 12},
    "4":  {"strategy_id": "4",  "paused": false, "epsilon": 0.2000, "qtable_states": 0},
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
  "strategy_id":   "1",
  "paused":        false,
  "epsilon":       0.1980,
  "alpha":         0.0990,
  "qtable_states": 5
}
```

---

## `POST /api/strategy/{id}/pause` / `POST /api/strategy/{id}/resume`

Pausa o reactiva el agente. Pausado = deja de aprender, sigue recibiendo senales.

```powershell
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/pause  -Method POST
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/resume -Method POST
```

---

## `POST /api/strategy/{id}/update`

Aprendizaje manual — para correcciones o trades que el bot no capturo.

**Con state y action explicitos:**
```json
{
  "order_id":    "20260518_142300123456",
  "pnl_pct":     1.45,
  "duration_min": 47.0,
  "state":       "wide|strong|far",
  "action":      "EXECUTE_FULL"
}
```

**Campos:**

| Campo        | Tipo   | Requerido | Descripcion                    |
|--------------|--------|-----------|--------------------------------|
| order_id     | string | Si        | event_id del trade             |
| pnl_pct      | float  | Si        | PnL en % (positivo = ganancia) |
| duration_min | float  | No        | Duracion en minutos            |
| state        | string | No        | Estado al entrar               |
| action       | string | No        | Accion tomada                  |

---

## `GET /api/strategy/{id}/journal`

Resumen del diario de aprendizaje.

```json
{
  "strategy_id":    "1",
  "total_updates":  12,
  "blocked_states": [{"state": "tight|flat|near", "action": "EXECUTE_FULL", "q": -0.42}],
  "best_states":    [{"state": "wide|strong|far",  "action": "EXECUTE_FULL", "q": 0.38}],
  "recent_conclusions": ["..."]
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

Posiciones siendo monitoreadas por el Price Poller (estrategias 5-10).
Las estrategias 1, 2, 3, 4 no aparecen aqui — cierran por alerta TradingView.

```json
{
  "pending": {
    "20260518_142300123456": {
      "symbol":      "SOLUSDT",
      "side":        "buy",
      "entry_price": 93.73,
      "sl":          93.63,
      "tp":          93.93,
      "state":       "high|excellent|us",
      "strategy_id": "5"
    }
  },
  "count": 1
}
```

---

## Comandos utiles PowerShell

```powershell
# Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# Estado de todas las estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# Estado de estrategia especifica
Invoke-WebRequest http://localhost:8001/api/strategy/1/status | Select-Object -ExpandProperty Content

# Journal de aprendizaje
Invoke-WebRequest http://localhost:8001/api/strategy/1/journal | Select-Object -ExpandProperty Content

# Ver INSIGHTS
Get-Content logs\1\INSIGHTS.md
Get-Content logs\4\INSIGHTS.md

# Posiciones activas (estrategias 5-10)
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```
