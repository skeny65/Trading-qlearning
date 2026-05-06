# Data Schemas

## `data/qlearning/q_table.json`

Q-table persistida en disco. Formato:

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

- **Clave outer:** estado codificado `"regime|volatility|momentum"`
- **Clave inner:** una de `EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT`
- **Valor:** Q-value (float, puede ser negativo)
- Inicializado en `0.0` de forma lazy cuando se visita el estado por primera vez

## `data/qlearning/qlearning_stats.json`

Hiperparametros actuales del agente:

```json
{
  "alpha":        0.09,
  "epsilon":      0.18,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-03T14:30:00"
}
```

## `data/qlearning/replay_buffer.jsonl`

Una experiencia por linea (JSONL):

```json
{"ts":"2026-05-03T14:35:22","s":"trend_up|mid|bullish","a":"EXECUTE_FULL","r":1.15,"s_next":"range|mid|neutral","done":false}
{"ts":"2026-05-03T16:12:00","s":"range|low|neutral","a":"SKIP","r":-0.05,"s_next":"range|low|neutral","done":true}
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

Backups automaticos de la Q-Table:

```
q_table_20260503_060000.json
q_table_20260503_120000.json
q_table_20260503_180000.json
...
```

Formato identico a `q_table.json`. Se mantienen los ultimos 28 (7 dias x 4/dia).

## `data/bot_status.json`

Estado de las estrategias registradas:

```json
{
  "strategy_tv_qlearning": {
    "status": "active",
    "paused_reason": null,
    "last_trade": "2026-05-03T14:35:22"
  }
}
```
