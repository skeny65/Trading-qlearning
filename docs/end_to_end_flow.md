# Flujo End-to-End - bot3 Multi-Strategy

Hay dos flujos de operacion segun la estrategia:

| Estrategias | Flujo de cierre               | Aprendizaje Q         |
|-------------|-------------------------------|-----------------------|
| 1 y 2       | 2 alertas (open + close)      | Inmediato al recibir close |
| 3 a 10      | 1 alerta + Price Poller       | Cuando Binance detecta TP/SL |

---

## Flujo A: Estrategias 1 y 2 — 2 alertas por operacion

### Alerta 1: APERTURA

```
+-------------------+
|   TradingView     |
|   signal_type:    |
|   "open"          |
+--------+----------+
         |
         |  POST /webhook/strategy/1  (o /2)
         |  Body: {signal_type:"open", action:"buy", params:{f1,f2,f3,...}}
         v
+-----------------------------------------------------------+
|              bot3.py -- localhost:8001                    |
|                                                           |
|  1. Verificar secret                                      |
|  2. Detecta signal_type="open" -> flujo Q-Learning        |
|  3. worker.decide(body):                                  |
|     Estrategia 1: encode_state -> f1_level|f2_level|f3_level|
|     Estrategia 2: encode_state -> regime|momentum|setup|htf|strength|
|     agent.choose_action(state) [epsilon-greedy]           |
|     -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT        |
|                                                           |
|  4. Escribe fila en Excel (result=VACIO todavia)          |
|  5. Si ejecuta:                                           |
|     -> Envia a bot1 en background                         |
|     -> open_positions[(id, symbol)] = {state, action}     |
|     -> pending_q_decisions[order_id] = {state, action...} |
+-----------------------------------------------------------+
```

### Alerta 2: CIERRE

```
+-------------------+
|   TradingView     |
|   signal_type:    |
|   "close"         |
+--------+----------+
         |
         |  POST /webhook/strategy/1  (o /2)
         |  Body: {signal_type:"close", action:"close_buy",
         |         params:{price, entry_price, pnl_pct, close_reason}}
         v
+-----------------------------------------------------------+
|              bot3.py -- localhost:8001                    |
|                                                           |
|  1. Detecta signal_type="close" -> bypass Q-Learning      |
|  2. Recupera open_positions[(id, symbol)]                 |
|     -> state y action de cuando se abrio                  |
|  3. Envia orden de cierre a bot1 (background)             |
|  4. _send_close_to_bot1():                                |
|     - compute_reward(pnl_pct, duration_min)               |
|     - worker.update_q(state, action, reward) INMEDIATO    |
|       -> Bellman: Q(s,a) += alpha*[r + gamma*maxQ' - Q(s,a)]|
|       -> agent.decay_params() -> epsilon y alpha decaen   |
|       -> INSIGHTS.md regenerado                           |
|     - update_excel_result(order_id, WIN/LOSS) INMEDIATO   |
|       -> pnl_notes = "+0.50% | CROSS | 32min"             |
|     - Elimina de open_positions y pending_q_decisions     |
+-----------------------------------------------------------+
```

---

## Flujo B: Estrategias 3-10 — 1 alerta + Price Poller

```
+-------------------+
|   TradingView     |
|   (1 alerta)      |
+--------+----------+
         |
         |  POST /webhook/strategy/3  (o /4 ... /10)
         |  Body: {action:"buy", params:{price, sl, tp, ...}}
         v
+-----------------------------------------------------------+
|              bot3.py -- localhost:8001                    |
|                                                           |
|  1. Detecta signal_type ausente o "open" -> flujo Q       |
|  2. worker.decide(body) -> EXECUTE / SKIP / ...           |
|  3. Si ejecuta:                                           |
|     -> Envia a bot1                                       |
|     -> pending_q_decisions[order_id] = {                  |
|         state, action, entry_price, sl, tp, open_time     |
|       }                                                   |
+-----------------------------------------------------------+
                         |
                         v
+-----------------------------------------------------------+
|  manager/price_poller.py  (hilo daemon, cada 60s)         |
|                                                           |
|  GET https://api.binance.com/api/v3/ticker/price          |
|  Sin API key                                              |
|                                                           |
|  Para cada pending con sl + tp:                           |
|    BUY:  precio >= tp -> WIN  |  precio <= sl -> LOSS     |
|    SELL: precio <= tp -> WIN  |  precio >= sl -> LOSS     |
|    > 24h sin cierre   -> EXPIRED (LOSS)                   |
|                                                           |
|  Al detectar cierre -> _close_position():                 |
|    1. worker.update_q(state, action, reward, next_state)  |
|    2. update_excel_result(order_id, WIN/LOSS, pnl_notes)  |
|       pnl_notes = "+2.34% | TP_HIT | 47min | R=2.34x"    |
+-----------------------------------------------------------+
```

---

## Resultado en Excel (automatico en ambos flujos)

| timestamp_utc        | symbol  | ql_action    | ql_state          | execute | result   | pnl_notes                      | learned_at           |
|----------------------|---------|--------------|-------------------|---------|----------|--------------------------------|----------------------|
| 2026-05-16T07:20:00Z | SOLUSDT | EXECUTE_FULL | wide\|strong\|far  | True    | **LOSS** | **-0.29% \| CROSS \| 32min**  | 2026-05-16T07:52:00Z |
| 2026-05-16T13:00:00Z | SOLUSDT | EXECUTE_FULL | wide\|strong\|mid  | True    | **WIN**  | **+1.45% \| TP_HIT \| 47min** | 2026-05-16T13:47:00Z |

**El Excel se llena automaticamente. No necesitas hacer nada.**

---

## Flujo de revision manual en Excel (siempre disponible)

Si necesitas corregir un resultado o aprender de un trade que el bot no capturo:

```
1. Abre logs/{id}/trade_log.xlsx
2. En columna 'result': escribe WIN o LOSS en la fila que quieras
3. Guarda el Excel
4. Corre: python scripts/learn_from_excel.py
   -> Lee filas con WIN/LOSS y learned_at vacio
   -> Llama POST /api/strategy/{id}/update por cada una
   -> El agente aprende y regenera INSIGHTS.md
   -> Marca learned_at en Excel (no reprocesa)
```

```powershell
# Ver que se procesaria sin hacer nada
python scripts/learn_from_excel.py --dry-run

# Procesar todas las estrategias
python scripts/learn_from_excel.py

# Solo una estrategia
python scripts/learn_from_excel.py 1
python scripts/learn_from_excel.py 2
```

---

## INSIGHTS.md - Lo que aprende el agente (estrategia 1 como ejemplo)

Despues de suficientes trades, `logs/1/INSIGHTS.md` muestra automaticamente:

```
## Contextos RENTABLES

| Estado              | Accion       | Q-value |
|---------------------|--------------|---------|
| wide|strong|far     | EXECUTE_FULL | +0.3842 |
| wide|mid|far        | EXECUTE_FULL | +0.2100 |

Sugerencia: Prioriza señales cuando f1>=0.5%, f2>=0.2%, precio lejos de DEMA200.

## Contextos BLOQUEADOS

| Estado              | Accion evitada | Q-value |
|---------------------|----------------|---------|
| tight|flat|near     | EXECUTE_FULL   | -0.4200 |

Filtros sugeridos: Evitar entradas cuando f1<0.2%, f2<0.2%, precio cerca DEMA200.
```
