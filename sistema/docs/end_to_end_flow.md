# Flujo End-to-End - bot3 Multi-Strategy

## Resumen por estrategia

| Estrategias | Par     | Flujo de cierre          | Binance  | Aprendizaje Q         |
|-------------|---------|--------------------------|----------|-----------------------|
| 1           | SOLUSDT | 2 alertas (open + close) | LIVE     | Inmediato al cierre   |
| 2           | SOLUSDT | 2 alertas (open + close) | LEARN ONLY | Inmediato al cierre |
| 3           | SOLUSDT | 2 alertas (open + close) | LEARN ONLY | Inmediato al cierre |
| 4           | ETHUSDT | 2 alertas (open + close) | LIVE     | Inmediato al cierre   |
| 5-10        | varios  | 1 alerta + Price Poller  | LIVE     | Cuando Poller detecta TP/SL |

---

## Flujo A: Estrategias 1 y 4 — 2 alertas, ejecucion real en Binance

### Alerta 1: APERTURA

```
TradingView
  POST /webhook/strategy/1  (o /4)
  Body: {signal_type:"open", action:"buy"/"sell", params:{dist_brecha, pendiente_verde, dist_d300, price, sl, ...}}
         |
         v
bot3.py
  1. Verifica secret + status="pending"
  2. Detecta signal_type="open" -> flujo Q-Learning
  3. worker.encode_state(params):
       dist_brecha=0.627  -> "wide"
       pendiente_verde=0.906 (abs) -> "strong"
       dist_d300=1.701    -> "far"
       estado = "wide|strong|far"
  4. agent.choose_action(estado) [epsilon-greedy]
       Q-table nueva -> todos Q=0 -> elige EXECUTE_FULL
       Con experiencia -> elige la accion con mayor Q-value
  5. Si EXECUTE_FULL o EXECUTE_HALF o INVERT:
       [background] binance_executor.open_position(symbol, side, price, None, None)
         * get_usdt_balance()     -> balance en vivo
         * margin = balance * 0.95 -> 95% del balance (5% para fees)
         * notional = margin * 25 -> leverage x25
         * qty = notional / price -> redondeado al step de Binance
         * futures_change_leverage(25)
         * MARKET BUY qty
         * (sin SL/TP para estrategias 1,2,3,4 — TradingView gestiona cierre)
       open_positions[("1","SOLUSDT")] = {state, action, side, entry_price, open_time}
       Excel: fila nueva con result="PENDING", pnl_pct="PENDING"
  6. Si SKIP: registra en Excel y sale sin tocar Binance
  7. Responde a TradingView: {"ok": true}
```

### Alerta 2: CIERRE

```
TradingView
  POST /webhook/strategy/1  (o /4)
  Body: {signal_type:"close", action:"close_buy"/"close_sell",
         params:{price, entry_price, pnl_pct, close_reason}}
         |
         v
bot3.py
  1. Detecta signal_type="close" -> bypass Q-Learning
  2. Recupera open_positions[("1","SOLUSDT")]
       -> state="wide|strong|far", action="EXECUTE_FULL", open_time=...
  3. [background] binance_executor.close_position(symbol)
       * cancel_open_orders(symbol)  -> cancela SL/TP colgados
       * get_position_qty(symbol)    -> qty real de Binance
       * MARKET SELL qty reduceOnly
  4. compute_reward(pnl_pct, duration_min)
  5. worker.update_q("wide|strong|far", "EXECUTE_FULL", reward)
       Bellman: Q(s,a) += alpha * [r + gamma*maxQ' - Q(s,a)]
       epsilon y alpha decaen con cada trade
       INSIGHTS.md regenerado
  6. update_excel_result(order_id, WIN/LOSS, pnl_pct, pnl_notes)
       result="WIN", pnl_pct="+0.47%", pnl_notes="ANTI_PARALLEL | 45min"
  7. Elimina de open_positions y pending_q_decisions
  8. Responde a TradingView: {"ok": true}
```

---

## Flujo B: Estrategias 2 y 3 — 2 alertas, LEARN ONLY

Identico al Flujo A, excepto:
- **Apertura:** el bot simula la orden (log `LEARN_ONLY`) sin llamar a Binance
- **Cierre:** no llama a `close_position()`, calcula reward y actualiza Q-table igual
- El Excel se llena igual: PENDING -> WIN/LOSS con pnl_pct
- El agente aprende exactamente igual que en LIVE

Util para acumular experiencia con senales reales sin arriesgar capital.

---

## Flujo C: Estrategias 5-10 — 1 alerta + Price Poller

```
TradingView
  POST /webhook/strategy/5  (o /6.../10)
  Body: {action:"buy", params:{price, sl, tp}}
         |
         v
bot3.py
  1. signal_type ausente o "open" -> flujo Q-Learning
  2. worker.encode_state -> estado scaffold (price_zone|rr_level|hour_zone)
  3. Si ejecuta: binance_executor.open_position(symbol, side, price, sl, tp)
       * MARKET entry + STOP_MARKET(sl) + TAKE_PROFIT_MARKET(tp)
  4. pending_q_decisions[order_id] = {state, action, entry_price, sl, tp, open_time}
  5. Responde: {"ok": true}
         |
         v (hilo daemon, cada 60s)
price_poller.py
  GET https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT
  Para cada pending (estrategias 5-10):
    BUY:  precio >= tp -> WIN  |  precio <= sl -> LOSS
    SELL: precio <= tp -> WIN  |  precio >= sl -> LOSS
    > 24h -> EXPIRED (LOSS)
  Al detectar:
    worker.update_q(state, action, reward)
    update_excel_result(WIN/LOSS, pnl_pct, pnl_notes)
    Elimina de pending_q_decisions
```

---

## Resultado en Excel (automatico en todos los flujos)

### Al abrir (inmediato):
| timestamp_utc | symbol | ql_action | ql_state | price | result | pnl_pct | pnl_notes |
|---|---|---|---|---|---|---|---|
| 2026-05-18T07:00:00Z | SOLUSDT | EXECUTE_FULL | wide\|strong\|far | 87.37 | PENDING | PENDING | PENDING |

### Al cerrar (automatico):
| timestamp_utc | symbol | ql_action | ql_state | price | result | pnl_pct | pnl_notes |
|---|---|---|---|---|---|---|---|
| 2026-05-18T07:00:00Z | SOLUSDT | EXECUTE_FULL | wide\|strong\|far | 87.37 | **WIN** | **+0.47%** | **ANTI_PARALLEL \| 45min** |

---

## Calculo de cantidad en Binance (automatico)

```
balance_disponible = get_usdt_balance()           # consulta en vivo antes de cada trade
margen             = balance * 0.95               # 95% del balance (5% para fees)
notional           = margen * 25                  # leverage x25
qty_raw            = notional / precio_entrada
qty                = redondear_hacia_abajo(qty_raw, step_size_binance)

Ejemplo con $92.43 USDT en SOLUSDT a $85.30:
  margen   = $92.43 * 0.95 = $87.81
  notional = $87.81 * 25   = $2,195.25
  qty_raw  = $2,195.25 / $85.30 = 25.73 SOL
  qty      = 25.7 SOL  (step=0.1)
  margen_real = 25.7 * $85.30 / 25 = $87.70 USDT
```

El balance se consulta en tiempo real antes de cada trade. Si ganas $2, la proxima
orden usa $94.43 — el efecto compuesto es automatico.
