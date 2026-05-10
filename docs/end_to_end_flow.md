# Flujo End-to-End - bot3 Multi-Strategy

## Flujo completo: TradingView -> Q-Learning -> bot1 -> aprendizaje automatico

```
+-------------------+
|   TradingView     |
|   .pine alert     |
+--------+----------+
         |
         |  POST http://<ngrok>/webhook/strategy/qlearning
         |  Header: X-Webhook-Secret: <TV_WEBHOOK_SECRET>
         |  Body: JSON con symbol, action, price, sl, tp, params...
         v
+-----------------------------------------------------------+
|              bot3.py -- localhost:8001                    |
|                                                           |
|  1. Verificar X-Webhook-Secret (401 si falla)             |
|  2. Verificar IP si TV_ENFORCE_IP=true (403 si falla)     |
|  3. Si status != "pending" -> 200 silente                 |
|                                                           |
|  4. StrategyRegistry.get("qlearning") -> QLearningWorker  |
|                                                           |
|  5. worker.decide(body):                                  |
|     encode_state(params) -> "trend_up|bullish|breakout|   |
|                               bull|extreme"               |
|     agent.choose_action(state) [epsilon-greedy]           |
|     -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT        |
|                                                           |
|  6. Escribe fila en Excel:                                |
|     logs/qlearning/trade_log.xlsx                         |
|     [result=VACIO | pnl_notes=VACIO | learned_at=VACIO]   |
|                                                           |
|  7. Si execute=True:                                      |
|     webhook_client.send() -> POST /webhook/bot3           |
|     pending_q_decisions[order_id] = {                     |
|       strategy_id, state, action,                         |
|       entry_price, sl, tp, symbol, side, open_time        |
|     }                                                     |
|     (se registra aunque bot1 este caido)                  |
+----------------------------+------------------------------+
                             |
                             | POST localhost:8000/webhook/bot3
                             v
+-----------------------------------------------------------+
|   bot1.py -- localhost:8000  (opcional / independiente)   |
|   Ejecuta en Alpaca si esta disponible                    |
+-----------------------------------------------------------+
```

---

## Flujo de aprendizaje automatico (Price Poller)

El Price Poller corre en segundo plano cada **60 segundos**, completamente
independiente. No requiere bot1 ni intervencion humana.

```
+-----------------------------------------------------------+
|  manager/price_poller.py  (hilo daemon, cada 60s)         |
|                                                           |
|  Para cada pending_q_decisions con entry_price+sl+tp:     |
|                                                           |
|    GET https://api.binance.com/api/v3/ticker/price        |
|        ?symbol=SOLUSDT                                    |
|    -> precio actual en tiempo real                        |
|                                                           |
|    Evaluar:                                               |
|      BUY:  precio >= tp -> TP_HIT (resultado WIN)         |
|            precio <= sl -> SL_HIT (resultado LOSS)        |
|      SELL: precio <= tp -> TP_HIT (resultado WIN)         |
|            precio >= sl -> SL_HIT (resultado LOSS)        |
|      > 24h sin cierre   -> EXPIRED (resultado LOSS)       |
|                                                           |
|  Al detectar cierre -> _close_position():                 |
|                                                           |
|    1. Calcular pnl_pct y R-multiple                       |
|    2. worker.update_q(state, action, reward, next_state)  |
|       Bellman: Q(s,a) += alpha*[r + gamma*maxQ' - Q(s,a)] |
|       agent.decay_params() -> epsilon y alpha decaen      |
|       trainer.append_experience() -> replay_buffer.jsonl  |
|       trainer.save_and_backup() -> q_table.json           |
|       journal.record_update() -> learning_journal.jsonl   |
|                              -> INSIGHTS.md (regenerado)  |
|                                                           |
|    3. update_excel_result(order_id, result, pnl_notes)    |
|       Abre logs/{id}/trade_log.xlsx                       |
|       Busca la fila por order_id                          |
|       Escribe automaticamente:                            |
|         result    = "WIN" o "LOSS"                        |
|         pnl_notes = "+2.34% | TP_HIT | 47min | R=2.34x"  |
|         learned_at = timestamp UTC                        |
|       Guarda Excel                                        |
+-----------------------------------------------------------+
```

---

## Resultado final en Excel (automatico)

Despues de que el Price Poller detecta el cierre, el Excel se ve asi:

| timestamp_utc | symbol | ql_action | ql_state | execute | result | pnl_notes | learned_at |
|---|---|---|---|---|---|---|---|
| 2026-05-09T14:23:00Z | SOLUSDT | EXECUTE_FULL | trend_up\|bullish\|... | True | **WIN** | **+1.45% \| TP_HIT \| 47min \| R=2.34x** | 2026-05-09T15:10:00Z |
| 2026-05-09T09:11:00Z | SOLUSDT | EXECUTE_FULL | range\|bearish\|... | True | **LOSS** | **-1.10% \| SL_HIT \| 22min \| R=-1.10x** | 2026-05-09T09:33:00Z |

**El Excel se llena solo. No necesitas hacer nada.**

---

## Flujo de revision manual en Excel (opcional / sin bot1)

Si quieres revisar o corregir resultados manualmente:

```
1. Abre logs/{id}/trade_log.xlsx
2. En columna 'result': escribe WIN o LOSS en las filas que quieras corregir
3. Opcional: escribe notas en 'pnl_notes'
4. Guarda el Excel
5. Corre: python scripts/learn_from_excel.py
   -> Lee filas con WIN/LOSS y learned_at vacio
   -> Llama POST /api/strategy/{id}/update por cada una
   -> El agente aprende y regenera INSIGHTS.md
   -> Marca learned_at en Excel (no reprocesa)
```

**Comandos del script:**
```powershell
# Ver que se procesaria sin hacer nada
python scripts/learn_from_excel.py --dry-run

# Procesar todas las estrategias
python scripts/learn_from_excel.py

# Solo una estrategia
python scripts/learn_from_excel.py qlearning
```

---

## Aprendizaje via API (avanzado)

Forzar aprendizaje directamente con state y action:

```powershell
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    order_id      = "20260509_142300123456"
    pnl_pct       = 1.45
    duration_min  = 47.0
    r_multiple    = 2.34
    state         = "trend_up|bullish|breakout|bull|extreme"
    action        = "EXECUTE_FULL"
} | ConvertTo-Json

Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/update `
    -Method POST -Headers $headers -Body $body
```

---

## INSIGHTS.md - Lo que aprende el agente

Despues de suficientes trades, `logs/qlearning/INSIGHTS.md` muestra automaticamente:

```
## Contextos RENTABLES

| Estado                                 | Accion       | Q-value |
|----------------------------------------|--------------|---------|
| trend_up|bullish|breakout|bull|extreme | EXECUTE_FULL | +0.3842 |

Sugerencia para TradingView:
Prioriza alertas en: trend_up + bullish + breakout + bull + extreme.

## Contextos BLOQUEADOS

| Estado                           | Accion evitada | Q-value |
|----------------------------------|----------------|---------|
| range|bearish|pullback|bear|weak | EXECUTE_FULL   | -0.4200 |

Filtros sugeridos para Pine Script:
- Evitar entradas cuando: range + bearish + pullback + bear + weak
```
