# Data Schemas

## `data/qlearning/q_table.json`

Q-table persistida en disco. Formato:

```json
{
  "trend_up|mid|bullish": {
    "EXECUTE_FULL": 0.0,
    "EXECUTE_HALF": 0.0,
    "SKIP":         0.0,
    "INVERT":       0.0
  }
}
```

- **Clave outer:** estado codificado `"regime|volatility|momentum"`
- **Clave inner:** una de `EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT`
- **Valor:** Q-value (float, puede ser negativo)
- Inicializado en `0.0` de forma lazy cuando se visita el estado por primera vez
- Estado actual (2026-05-06): 1 estado visitado (`trend_up|mid|bullish`), todos en 0.0

Con mas trades los Q-values divergeran a medida que el agente aprende:
```json
{
  "trend_up|mid|bullish": {
    "EXECUTE_FULL": 0.12345,
    "EXECUTE_HALF": 0.05000,
    "SKIP":        -0.02000,
    "INVERT":      -0.08000
  },
  "range|low|neutral": {
    "EXECUTE_FULL": -0.03000,
    "EXECUTE_HALF":  0.01000,
    "SKIP":          0.07500,
    "INVERT":       -0.01000
  }
}
```

## `data/qlearning/qlearning_stats.json`

Hiperparametros actuales del agente:

```json
{
  "alpha":        0.10,
  "epsilon":      0.20,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-06T21:17:39"
}
```

## `data/qlearning/replay_buffer.jsonl`

Una experiencia por linea (JSONL). Se llena con `POST /qlearning/update`:

```json
{"ts":"2026-05-06T21:17:39","s":"trend_up|mid|bullish","a":"EXECUTE_FULL","r":0.45,"s_next":"range|mid|neutral","done":false}
{"ts":"2026-05-06T22:30:00","s":"range|low|neutral","a":"SKIP","r":-0.05,"s_next":"range|low|neutral","done":true}
```

| Campo  | Tipo    | Descripcion                                              |
|--------|---------|----------------------------------------------------------|
| ts     | str     | timestamp UTC de cuando se cerro la posicion             |
| s      | str     | estado al entrar en la operacion                         |
| a      | str     | accion tomada por el agente                              |
| r      | float   | recompensa calculada por `compute_reward()`              |
| s_next | str     | estado del mercado al cerrar (o mismo estado si desconocido) |
| done   | bool    | true si el episodio termino sin s_next real              |

## `data/qlearning/backups/`

Backups automaticos de la Q-Table (cada 6 horas, max 28):

```
q_table_20260506_060000.json
q_table_20260506_120000.json
q_table_20260506_180000.json
...
```

Formato identico a `q_table.json`. Se mantienen los ultimos 28 (7 dias x 4/dia).

## `state/decision_log.jsonl`

Historial de todas las decisiones tomadas por bot3:

```json
{
  "event_id":   "uuid",
  "ql_action":  "EXECUTE_FULL",
  "state":      "trend_up|mid|bullish",
  "symbol":     "SPY",
  "side":       "buy",
  "size":       0.1,
  "order_id":   "759b9684-528d-47cc-b54a-98aa68003a5a",
  "timestamp":  "2026-05-06T21:17:39.517354+00:00",
  "dry_run":    false
}
```

## `state/pending_signals.json`

Senales que no pudieron enviarse a bot1 (fallo de red). Se reintentan al reiniciar bot3:

```json
[
  {
    "payload":   {...},
    "timestamp": "2026-05-06T21:17:39Z",
    "attempts":  2
  }
]
```
