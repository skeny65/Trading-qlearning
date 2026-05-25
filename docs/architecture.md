# Arquitectura de bot3 - Multi-Strategy Q-Learning

## Estado: OPERATIVO (2026-05-18)

## Principio de diseno

Cada estrategia es completamente independiente:
- Cada una tiene su propia Q-table, agente, logs y Excel
- bot3 ejecuta ordenes DIRECTAMENTE en Binance Futures USDT-M (sin intermediarios)
- Las estrategias 1, 2, 3 y 4 usan flujo de **2 alertas** (open + close desde TradingView)
- Las estrategias 5-10 usan flujo de **1 alerta** + Price Poller para detectar el cierre
- Estrategias 2 y 3 aprenden pero NO ejecutan en Binance (LEARN_ONLY)

## Estrategias registradas

| ID  | Par      | Estado Q                              | Flujo de cierre          | Ejecuta en Binance |
|-----|----------|---------------------------------------|--------------------------|-------------------|
| 1   | SOLUSDT  | 3D: f1_sep\|f2_angle\|f3_d200 (27)   | Alerta close TradingView | SI (LIVE)         |
| 2   | SOLUSDT  | 5D: regime\|momentum\|... (243)       | Alerta close TradingView | NO (LEARN_ONLY)   |
| 3   | SOLUSDT  | 3D: entry_strength\|bar_zone\|pattern | Alerta close TradingView | NO (LEARN_ONLY)   |
| 4   | ETHUSDT  | 3D: f1_sep\|f2_angle\|f3_d200 (27)   | Alerta close TradingView | SI (LIVE)         |
| 5-10| -        | 3D: scaffold (27)                     | Price Poller (sl/tp)     | SI (LIVE)         |

---

## Diagrama de Componentes

```
+----------------------------------------------------------------+
|                  TradingView PineScript                        |
|  POST https://<ngrok>/webhook/strategy/{id}?secret=<secret>   |
+------------------------+---------------------------------------+
                         |
                         v
+----------------------------------------------------------------+
|                    bot3.py  (FastAPI :8001)                    |
|                                                                |
|  FASE 1: Validacion                                            |
|    Verificar secret + IP + status="pending"                    |
|                                                                |
|  FASE 2: StrategyRegistry.get(strategy_id)                     |
|    "1"  -> ApuestaWorker    (SOLUSDT, 3D, 2 alertas, LIVE)    |
|    "2"  -> QLearningWorker  (SOLUSDT, 5D, 2 alertas, LEARN)   |
|    "3"  -> TanqueWorker     (SOLUSDT, 3D, 2 alertas, LEARN)   |
|    "4"  -> Strategy4Worker  (ETHUSDT, 3D, 2 alertas, LIVE)    |
|    "5"->"10" -> ScaffoldWorker (3D, 1 alerta, LIVE)           |
|                                                                |
|  FASE 3: Routing por signal_type                               |
|    signal_type="open"  -> worker.decide() (Q-Learning)         |
|    signal_type="close" -> cierre inmediato (bypass Q)          |
|                                                                |
|  FASE 4a: Apertura (signal_type="open")                        |
|    encode_state(params) -> estado Q                            |
|    agent.choose_action(estado) [epsilon-greedy]                |
|    -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT              |
|    Si ejecuta:                                                 |
|      - LIVE: binance_executor.open_position()                  |
|        * balance disponible x 99% = margen                     |
|        * margen x leverage(25) = notional                      |
|        * MARKET entry + optional STOP_MARKET + TP_MARKET       |
|      - LEARN_ONLY (2,3): simula sin tocar Binance              |
|      open_positions[(id, symbol)] = {state, action, ...}       |
|                                                                |
|  FASE 4b: Cierre (signal_type="close") [estrategias 1,2,3,4]  |
|    Recupera state/action de open_positions                     |
|    - LIVE: binance_executor.close_position(symbol)             |
|      * cancel_open_orders -> MARKET reduceOnly                 |
|    - LEARN_ONLY: simula cierre sin tocar Binance               |
|    compute_reward(pnl_pct, duration_min)                       |
|    worker.update_q() -> Bellman inmediato                      |
|    update_excel_result(WIN/LOSS, pnl_pct, pnl_notes)          |
|                                                                |
|  FASE 5: Persistencia (siempre)                                |
|    logs/{id}/trade_log.xlsx  <- fila nueva (result=PENDING)    |
|    state/{id}/decision_log.jsonl                               |
|    logs/{id}/events/YYYY-MM-DD_HH-MM-SS.json                  |
|                                                                |
|  RESPUESTA a TradingView: {"ok": true}  (siempre)             |
+----------------------------------------------------------------+
                         |
                (Binance Futures USDT-M)
                         v
+----------------------------------------------------------------+
|   core/binance_executor.py                                     |
|                                                                |
|   open_position(symbol, side, price, sl, tp):                  |
|     1. get_usdt_balance()  -> balance en vivo                  |
|     2. margin = balance * 0.99                                 |
|     3. qty = (margin * 25) / price  [step size de Binance]    |
|     4. futures_change_leverage(symbol, 25)                     |
|     5. MARKET BUY/SELL qty                                     |
|     6. STOP_MARKET closePosition=True  (si sl > 0)            |
|     7. TAKE_PROFIT_MARKET closePosition=True  (si tp > 0)     |
|                                                                |
|   close_position(symbol):                                      |
|     1. futures_cancel_all_open_orders(symbol)                  |
|     2. get_position_qty(symbol)  -> qty real                   |
|     3. MARKET SELL/BUY qty reduceOnly=True                     |
+----------------------------------------------------------------+


PRICE POLLER (hilo independiente, cada 60 segundos):
Solo activo para estrategias 5-10. Las estrategias 1,2,3,4 excluidas.

+----------------------------------------------------------------+
|  manager/price_poller.py                                       |
|                                                                |
|  SELF_CLOSING_STRATEGIES = {"1","2","3","4"}  <- excluidas    |
|  Fuente: https://api.binance.com/api/v3/ticker/price           |
|  Sin API key, gratuito, tiempo real                            |
|                                                                |
|  Para cada pending (estrategias 5-10) con entry_price+sl+tp:  |
|    BUY:  precio >= tp -> WIN  |  precio <= sl -> LOSS          |
|    SELL: precio <= tp -> WIN  |  precio >= sl -> LOSS          |
|    > 24h sin cierre   -> EXPIRED (LOSS)                        |
|                                                                |
|  Al detectar cierre:                                           |
|    worker.update_q(state, action, reward)                      |
|    update_excel_result(order_id, result, pnl_pct, pnl_notes)  |
+----------------------------------------------------------------+


ESTADO EN DISCO (por estrategia, id = 1 a 10):

  data/strategies/{id}/
    q_table.json             Q-Table persistida
    qlearning_stats.json     epsilon, alpha actuales
    replay_buffer.jsonl      historial de experiencias
    backups/                 snapshots automaticos cada 6h

  state/{id}/
    decision_log.jsonl       historial de decisiones

  logs/{id}/
    trade_log.xlsx           Excel — result/pnl_pct/pnl_notes llenados al cierre
    INSIGHTS.md              resumen de aprendizaje (regenerado tras cada Q-update)
    learning_journal.jsonl   registro detallado por Q-update
    events/                  reporte JSON por evento
```

---

## Configuracion activa (.env)

| Variable             | Valor  | Descripcion                                  |
|----------------------|--------|----------------------------------------------|
| BINANCE_LEVERAGE     | 25     | Apalancamiento para todas las ordenes        |
| BINANCE_MAX_MARGIN_PCT | 0.99 | 99% del balance disponible por trade         |
| BINANCE_TESTNET      | false  | Cuenta real de Binance                       |
| DRY_RUN              | false  | Operaciones reales                           |
| POLL_INTERVAL_SEC    | 60     | Frecuencia del Price Poller                  |

## Independencia de componentes

| Componente       | Depende de              | Comportamiento si cae                    |
|------------------|-------------------------|------------------------------------------|
| bot3             | Python, .env            | start_bot3.bat lo reinicia en 5s        |
| Binance executor | API key + internet      | Loguea error, no crashea el bot         |
| Price Poller     | API publica Binance     | Reintenta en el siguiente ciclo (60s)   |
| Excel update     | openpyxl                | Warning en log, no crashea              |
| TradingView      | ngrok activo            | Solo afecta entrada de senales          |
