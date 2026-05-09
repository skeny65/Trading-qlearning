# Data Schemas - bot3 Multi-Strategy

## Estructura de directorios de datos

```
data/
  strategies/
    {strategy_id}/            (apuesta | qlearning | tanque)
      q_table.json
      qlearning_stats.json
      replay_buffer.jsonl
      backups/

state/
  {strategy_id}/
    decision_log.jsonl
  pending_signals.json

logs/
  {strategy_id}/
    INSIGHTS.md
    learning_journal.jsonl
    trade_log.xlsx
    events/
      YYYY-MM-DD_HH-MM-SS.json
```

---

## `data/strategies/{id}/q_table.json`

Q-table persistida en disco. Formato:

```json
{
  "trend_up|bullish|breakout|bull|extreme": {
    "EXECUTE_FULL": 0.3842,
    "EXECUTE_HALF": 0.1200,
    "SKIP":        -0.0500,
    "INVERT":      -0.2100
  },
  "range|bearish|pullback|bear|weak": {
    "EXECUTE_FULL": -0.4200,
    "EXECUTE_HALF": -0.1500,
    "SKIP":          0.1800,
    "INVERT":        0.0300
  }
}
```

- **Clave outer:** estado codificado (formato depende de la estrategia)
- **Clave inner:** una de `EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT`
- **Valor:** Q-value (float, puede ser negativo)
- Se inicializa en `0.0` de forma lazy cuando se visita el estado por primera vez

**Formatos de estado por estrategia:**

| Estrategia | Formato                                         | Estados posibles |
|------------|-------------------------------------------------|------------------|
| qlearning  | `regime\|momentum\|setup_type\|htf_bias\|trend` | 243              |
| apuesta    | `price_zone\|rr_level\|hour_zone`               | 36               |
| tanque     | `entry_strength\|bar_zone\|pattern`             | 27               |

---

## `data/strategies/{id}/qlearning_stats.json`

Hiperparametros actuales del agente:

```json
{
  "alpha":        0.10,
  "epsilon":      0.20,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-08T14:23:00"
}
```

---

## `data/strategies/{id}/replay_buffer.jsonl`

Una experiencia por linea (JSONL). Se llena automaticamente tras cada Q-update:

```json
{"ts":"2026-05-08T14:23:00","s":"trend_up|bullish|breakout|bull|extreme","a":"EXECUTE_FULL","r":0.40,"s_next":"trend_up|bullish|breakout|bull|extreme","done":false}
{"ts":"2026-05-08T15:10:00","s":"range|bearish|pullback|bear|weak","a":"EXECUTE_FULL","r":-0.40,"s_next":"range|bearish|pullback|bear|weak","done":true}
```

| Campo  | Tipo    | Descripcion                                                     |
|--------|---------|-----------------------------------------------------------------|
| ts     | str     | timestamp UTC del cierre de la posicion                         |
| s      | str     | estado al entrar en la operacion                                |
| a      | str     | accion tomada por el agente                                     |
| r      | float   | recompensa (calculada por Price Poller o compute_reward())      |
| s_next | str     | estado al cerrar (mismo estado si no hay info real)             |
| done   | bool    | true si el episodio no tuvo s_next real                         |

---

## `data/strategies/{id}/backups/`

Backups automaticos de la Q-Table (cada vez que se guarda, max 28):

```
q_table_20260508_060000.json
q_table_20260508_120000.json
...
```

Formato identico a `q_table.json`. Se mantienen los ultimos 28 archivos.

---

## `state/{id}/decision_log.jsonl`

Historial de todas las decisiones tomadas por bot3 para la estrategia:

```json
{
  "event_id":       "uuid",
  "strategy_id":    "qlearning",
  "timestamp_utc":  "2026-05-08T14:23:00.000000+00:00",
  "symbol":         "SOLUSDT",
  "tv_action":      "buy",
  "ql_action":      "EXECUTE_FULL",
  "ql_state":       "trend_up|bullish|breakout|bull|extreme",
  "q_value":        0.3842,
  "execute":        true,
  "final_action":   "buy",
  "size":           0.1,
  "order_id":       "759b9684-528d-47cc-b54a-98aa68003a5a",
  "dry_run":        false,
  "reason":         "[qlearning] Q-Learning: execute full"
}
```

---

## `state/pending_signals.json`

Senales que no pudieron enviarse a bot1 (fallo de red). Se reintentan al reiniciar bot3:

```json
[
  {
    "payload":   {"timestamp": "...", "status": "pending", "signal": {...}},
    "timestamp": "2026-05-08T14:23:00Z",
    "attempts":  2
  }
]
```

---

## `logs/{id}/learning_journal.jsonl`

Una linea JSON por cada Q-update (cada vez que cierra una posicion):

```json
{
  "ts":           "2026-05-08T14:23:00.000000+00:00",
  "strategy_id":  "qlearning",
  "state":        "trend_up|bullish|breakout|bull|extreme",
  "action":       "EXECUTE_FULL",
  "reward":       0.4000,
  "old_q":        0.0000,
  "new_q":        0.0400,
  "delta_q":      0.0400,
  "blocked":      false,
  "good":         false,
  "conclusion":   "Q sube de 0.000 a 0.040 tras trade ganador (reward=+0.400). aprendiendo: datos insuficientes aun.",
  "trade_meta":   {
    "epsilon":    0.1980,
    "alpha":      0.0990,
    "symbol":     "SOLUSDT",
    "close_type": "TP_HIT"
  }
}
```

| Campo      | Tipo   | Descripcion                                       |
|------------|--------|---------------------------------------------------|
| ts         | str    | timestamp UTC del Q-update                        |
| state      | str    | estado al entrar en el trade                      |
| action     | str    | accion tomada                                     |
| reward     | float  | recompensa recibida                               |
| old_q      | float  | Q-value antes del update                          |
| new_q      | float  | Q-value despues del update                        |
| delta_q    | float  | cambio en el Q-value                              |
| blocked    | bool   | true si new_q < -0.30                             |
| good       | bool   | true si new_q > +0.30                             |
| conclusion | str    | texto legible generado automaticamente            |
| trade_meta | dict   | contexto extra: epsilon, alpha, symbol, close_type|

---

## `logs/{id}/INSIGHTS.md`

Archivo Markdown unico por estrategia, sobreescrito despues de cada Q-update.

Contiene:
1. Tabla de estados RENTABLES (Q > 0.30) con sugerencias de Pine Script
2. Tabla de estados BLOQUEADOS (Q < -0.30) con filtros sugeridos
3. Estadisticas del agente (epsilon, alpha, win rate historico)
4. Ultimas 15 conclusiones con tags `[RENTABLE]` / `[BLOQUEADO]`
5. Guia de uso del archivo

---

## `logs/{id}/events/YYYY-MM-DD_HH-MM-SS.json`

Reporte completo por evento (una alerta de TradingView):

```json
{
  "event_id":       "uuid",
  "timestamp_utc":  "2026-05-08T14:23:00Z",
  "strategy_id":    "qlearning",
  "mode":           "live",
  "symbol":         "SOLUSDT",
  "tv_action":      "buy",
  "ql_action":      "EXECUTE_FULL",
  "ql_state":       "trend_up|bullish|breakout|bull|extreme",
  "q_value":        0.3842,
  "execute":        true,
  "final_action":   "buy",
  "size":           0.1,
  "confidence":     0.7,
  "webhook_status": "executed",
  "order_id":       "759b9684-528d-47cc-b54a-98aa68003a5a",
  "reason":         "[qlearning] Q-Learning: execute full",
  "epsilon":        0.198,
  "alpha":          0.099,
  "params": {
    "price": 93.73, "sl": 93.63, "tp": 93.93,
    "regime": "trend_up", "momentum": "bullish",
    "setup_type": "breakout", "htf_bias": "bull",
    "trend_strength": "extreme"
  }
}
```
