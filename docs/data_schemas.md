# Data Schemas - bot3 Multi-Strategy

## Estructura de directorios de datos

```
data/
  strategies/
    {id}/            (apuesta | qlearning | tanque)
      q_table.json
      qlearning_stats.json
      replay_buffer.jsonl
      backups/

state/
  {id}/
    decision_log.jsonl
  pending_signals.json

logs/
  {id}/
    trade_log.xlsx        <- llenado automaticamente por Price Poller
    INSIGHTS.md
    learning_journal.jsonl
    events/
      YYYY-MM-DD_HH-MM-SS.json
```

---

## `logs/{id}/trade_log.xlsx`

Una fila por senal recibida de TradingView. El bot llena todas las columnas
automaticamente. Las columnas `result`, `pnl_notes` y `learned_at` las llena
el Price Poller cuando detecta TP o SL.

### Columnas que llena el bot al recibir la senal

| Columna        | Tipo    | Descripcion                                               |
|----------------|---------|-----------------------------------------------------------|
| timestamp_utc  | str     | Fecha y hora de la senal (ISO 8601 UTC)                   |
| event_id       | str     | ID unico del evento generado por bot3                     |
| strategy_id    | str     | apuesta / qlearning / tanque                              |
| mode           | str     | LIVE o DRY_RUN                                            |
| symbol         | str     | Par de trading (SOLUSDT, BTCUSDT, etc.)                   |
| tv_action      | str     | Accion de TradingView: buy / sell                         |
| ql_action      | str     | Decision Q-Learning: EXECUTE_FULL / HALF / SKIP / INVERT  |
| ql_state       | str     | Estado codificado (ej: "trend_up\|bullish\|breakout\|...")  |
| q_value        | float   | Valor Q del estado-accion elegido                         |
| regime         | str     | Regimen de mercado (si viene en params)                   |
| volatility     | str     | Volatilidad (si viene en params)                          |
| momentum       | str     | Momentum (si viene en params)                             |
| price          | float   | Precio de entrada                                         |
| sl             | float   | Stop Loss                                                 |
| tp             | float   | Take Profit                                               |
| atr            | float   | ATR en el momento de la senal                             |
| execute        | bool    | True si el bot decidio ejecutar (no SKIP)                 |
| final_action   | str     | Accion final: buy / sell / none                           |
| size           | float   | Tamano de la posicion enviada a bot1                      |
| confidence     | float   | Confianza de la senal TradingView (0-1)                   |
| webhook_status | str     | executed / dry_run / failed / skipped                     |
| order_id       | str     | UUID de bot1 o event_id si bot1 estaba caido              |
| reason         | str     | Descripcion de la decision Q-Learning                     |
| epsilon        | float   | Epsilon del agente al momento de decidir                  |
| alpha          | float   | Alpha del agente al momento de decidir                    |

### Columnas llenadas automaticamente por el Price Poller

| Columna     | Tipo | Descripcion                                                      |
|-------------|------|------------------------------------------------------------------|
| result      | str  | **WIN** o **LOSS** (llenado cuando Binance detecta TP o SL)     |
| pnl_notes   | str  | "+1.45% \| TP_HIT \| 47min \| R=2.34x" (detalle del cierre)    |
| learned_at  | str  | Timestamp UTC de cuando el agente proceso el resultado           |

**Nota:** Si el Excel esta abierto cuando el Price Poller intenta escribir,
muestra un warning y reintenta en el siguiente ciclo (60s). Cierra el Excel
para ver los resultados en tiempo real.

**Nota:** Si marcas manualmente WIN/LOSS antes de que llegue el Price Poller,
el bot NO sobreescribe tu decision (respeta el valor existente en `result`).

---

## `data/strategies/{id}/q_table.json`

Q-table persistida. Se actualiza automaticamente tras cada cierre de posicion.

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

**Formatos de estado por estrategia:**

| Estrategia | Formato de estado                                | Estados |
|------------|--------------------------------------------------|---------|
| qlearning  | `regime\|momentum\|setup_type\|htf_bias\|strength` | 243   |
| apuesta    | `price_zone\|rr_level\|hour_zone`                | 27      |
| tanque     | `entry_strength\|bar_zone\|pattern`              | 27      |

**Clasificacion automatica de estados:**
- Q > +0.30 -> RENTABLE (el agente prefiere ejecutar aqui)
- Q < -0.30 -> BLOQUEADO (el agente evita ejecutar aqui)

---

## `data/strategies/{id}/qlearning_stats.json`

```json
{
  "alpha":        0.10,
  "epsilon":      0.20,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-09T14:23:00"
}
```

---

## `data/strategies/{id}/replay_buffer.jsonl`

Una experiencia por linea. Se llena automaticamente por el Price Poller.

```json
{"ts":"2026-05-09T14:23:00","s":"trend_up|bullish|breakout|bull|extreme","a":"EXECUTE_FULL","r":0.40,"s_next":"trend_up|bullish|breakout|bull|extreme","done":false}
{"ts":"2026-05-09T15:10:00","s":"range|bearish|pullback|bear|weak","a":"EXECUTE_FULL","r":-0.55,"s_next":"range|bearish|pullback|bear|weak","done":true}
```

---

## `logs/{id}/learning_journal.jsonl`

Una linea JSON por cada Q-update:

```json
{
  "ts":          "2026-05-09T15:10:00.000000+00:00",
  "strategy_id": "qlearning",
  "state":       "trend_up|bullish|breakout|bull|extreme",
  "action":      "EXECUTE_FULL",
  "reward":      0.4000,
  "old_q":       0.0000,
  "new_q":       0.0400,
  "delta_q":     0.0400,
  "blocked":     false,
  "good":        false,
  "conclusion":  "Q sube de 0.000 a 0.040 tras trade ganador (reward=+0.400). aprendiendo.",
  "trade_meta":  {"epsilon": 0.198, "alpha": 0.099, "close_type": "TP_HIT"}
}
```

---

## `logs/{id}/INSIGHTS.md`

Archivo Markdown por estrategia, sobreescrito tras cada Q-update. Contiene:
1. Estados RENTABLES con sugerencias para Pine Script
2. Estados BLOQUEADOS con filtros sugeridos
3. Estadisticas del agente (epsilon, alpha, win rate)
4. Ultimas 15 conclusiones
