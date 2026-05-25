# Data Schemas - bot3 Multi-Strategy

## Estructura de directorios de datos

```
data/
  strategies/
    {id}/            (id = 1 al 10)
      q_table.json
      qlearning_stats.json
      replay_buffer.jsonl
      backups/

state/
  {id}/
    decision_log.jsonl

logs/
  {id}/
    trade_log.xlsx        <- result/pnl_pct/pnl_notes llenados automaticamente al cierre
    INSIGHTS.md           <- regenerado tras cada Q-update
    learning_journal.jsonl
    events/
      YYYY-MM-DD_HH-MM-SS.json
```

---

## `logs/{id}/trade_log.xlsx`

Una fila por señal recibida. Las columnas de cierre se pre-llenan como `PENDING`
al abrir y se actualizan automaticamente al cerrar.

### Columnas llenadas al recibir la señal de apertura

| Columna        | Tipo    | Descripcion                                               |
|----------------|---------|-----------------------------------------------------------|
| timestamp_utc  | str     | Fecha y hora de la señal (ISO 8601 UTC)                   |
| event_id       | str     | ID unico del evento generado por bot3                     |
| strategy_id    | str     | 1 / 2 / 3 / 4 / ... / 10                                 |
| mode           | str     | LIVE o DRY_RUN                                            |
| symbol         | str     | Par de trading (SOLUSDT, ETHUSDT, etc.)                   |
| tv_action      | str     | Accion de TradingView: buy / sell                         |
| ql_action      | str     | Decision Q-Learning: EXECUTE_FULL / HALF / SKIP / INVERT |
| ql_state       | str     | Estado codificado (ej: "wide\|strong\|far")               |
| q_value        | float   | Valor Q del estado-accion elegido                         |
| price          | float   | Precio de entrada                                         |
| sl             | float   | Stop Loss (si viene en params, 0 si no)                   |
| tp             | float   | Take Profit (si viene en params, 0 si no)                 |
| execute        | bool    | True si el bot decidio ejecutar (no SKIP)                 |
| final_action   | str     | Accion final: buy / sell / none                           |
| size           | float   | Fraccion de portafolio recibida de TradingView (0.1)      |
| webhook_status | str     | executed / dry_run / rejected / failed                    |
| order_id       | str     | order_id de Binance o event_id si DRY_RUN                 |
| reason         | str     | Descripcion de la decision Q-Learning                     |
| epsilon        | float   | Epsilon del agente al momento de decidir                  |
| alpha          | float   | Alpha del agente al momento de decidir                    |

### Columnas de cierre — PENDING al abrir, actualizadas automaticamente al cerrar

| Columna    | Tipo | Al abrir  | Al cerrar                                     |
|------------|------|-----------|-----------------------------------------------|
| result     | str  | PENDING   | WIN o LOSS                                    |
| pnl_pct    | str  | PENDING   | "+0.47%" o "-0.29%"                           |
| pnl_notes  | str  | PENDING   | "CROSS \| 32min" o "TP_HIT \| 47min \| R=2x" |
| learned_at | str  | (vacio)   | Timestamp UTC del cierre                      |

**Notas:**
- Si el Excel esta abierto cuando bot3 intenta escribir, muestra warning y registra en log.
- Si escribes manualmente WIN/LOSS antes del cierre automatico, el bot NO sobreescribe.
- PENDING se sobreescribe automaticamente — solo se respetan valores distintos de PENDING.

---

## Flujo de cierre por estrategia

| ID   | Estrategia  | Ejecucion  | Cierre                                    |
|------|-------------|------------|-------------------------------------------|
| 1    | SOLUSDT     | LIVE       | Alerta close TradingView -> inmediato     |
| 2    | SOLUSDT     | LEARN ONLY | Alerta close TradingView -> inmediato     |
| 3    | SOLUSDT     | LEARN ONLY | Alerta close TradingView -> inmediato     |
| 4    | ETHUSDT     | LIVE       | Alerta close TradingView -> inmediato     |
| 5-10 | varios      | LIVE       | Price Poller Binance cada 60s             |

---

## `data/strategies/{id}/q_table.json`

Q-table persistida. Se actualiza automaticamente tras cada cierre de posicion.

```json
{
  "wide|strong|far": {
    "EXECUTE_FULL": 0.3842,
    "EXECUTE_HALF": 0.1200,
    "SKIP":        -0.0500,
    "INVERT":      -0.2100
  },
  "tight|flat|near": {
    "EXECUTE_FULL": -0.4200,
    "EXECUTE_HALF": -0.1500,
    "SKIP":          0.1800,
    "INVERT":        0.0300
  }
}
```

**Formato de estado por estrategia:**

| ID   | Indicadores           | Formato de estado                                        | Estados |
|------|-----------------------|----------------------------------------------------------|---------|
| 1    | TEMA21/55 + DEMA200   | `f1_level\|f2_level\|f3_level`                           | 27      |
| 2    | QLearning 5D          | `regime\|momentum\|setup_type\|htf_bias\|trend_strength` | 243     |
| 3    | Tanque                | `entry_strength\|bar_zone\|pattern`                      | 27      |
| 4    | EMA9/21/200           | `f1_level\|f2_level\|f3_level`                           | 27      |
| 5-10 | Scaffold              | `price_zone\|rr_level\|hour_zone`                        | 27      |

**Clasificacion automatica de estados:**
- Q > +0.30 → RENTABLE (el agente prefiere ejecutar aqui)
- Q < -0.30 → BLOQUEADO (el agente evita ejecutar aqui)

---

## `data/strategies/{id}/qlearning_stats.json`

```json
{
  "alpha":        0.10,
  "epsilon":      0.20,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-18T14:23:00"
}
```

---

## `data/strategies/{id}/replay_buffer.jsonl`

Una experiencia por linea. Se llena tras cada Q-update.

```json
{"ts":"2026-05-18T14:23:00","s":"wide|strong|far","a":"EXECUTE_FULL","r":0.40,"s_next":"closed","done":false}
{"ts":"2026-05-18T13:00:00","s":"tight|flat|near","a":"EXECUTE_FULL","r":-0.55,"s_next":"closed","done":true}
```

---

## `logs/{id}/learning_journal.jsonl`

Una linea JSON por cada Q-update:

```json
{
  "ts":          "2026-05-18T14:55:00.000000+00:00",
  "strategy_id": "1",
  "state":       "wide|strong|far",
  "action":      "EXECUTE_FULL",
  "reward":      -0.3400,
  "old_q":       0.0000,
  "new_q":       -0.0340,
  "delta_q":     -0.0340,
  "blocked":     false,
  "good":        false,
  "conclusion":  "Q baja de 0.000 a -0.034 tras trade perdedor (reward=-0.340). aprendiendo.",
  "trade_meta":  {"close_reason": "cross", "pnl_pct": -0.29, "duration_min": 32}
}
```

---

## `logs/{id}/INSIGHTS.md`

Archivo Markdown por estrategia, sobreescrito tras cada Q-update. Contiene:
1. Estados RENTABLES con sugerencias para Pine Script
2. Estados BLOQUEADOS con filtros sugeridos
3. Estadisticas del agente (epsilon, alpha, win rate)
4. Ultimas 15 conclusiones con timestamps
