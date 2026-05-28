# Arquitectura — bot_ejecutor

## Estado: OPERATIVO (2026-05-27)

## Principio de diseno

El bot_ejecutor recibe senales de TradingView y ejecuta ordenes directamente en Binance Futures.
Cada estrategia es completamente independiente — su propio motor de decision, logs y Excel.

- Estrategias 1 y 4: LIVE, flujo de 2 alertas (open + close desde TradingView), sin SL/TP en Binance
- Estrategias 2 y 3: LEARN ONLY, aprenden sin ejecutar en Binance, flujo de 2 alertas
- Estrategias 5-10: LIVE, 1 alerta de entrada + Price Poller detecta TP/SL cada 60s

## Estrategias registradas

| ID   | Par     | Estado             | Flujo de cierre          | Ejecuta en Binance | SL/TP en Binance          |
|------|---------|--------------------|--------------------------|--------------------|---------------------------|
| 1    | SOLUSDT | brecha\|pendiente\|d300 (27 estados) | Alerta close TradingView | SI (LIVE) | NO — TradingView gestiona |
| 2    | SOLUSDT | 5D: regime\|momentum\|... (243 estados) | Alerta close TradingView | NO (LEARN ONLY) | N/A |
| 3    | SOLUSDT | entry_strength\|bar_zone\|pattern (27) | Alerta close TradingView | NO (LEARN ONLY) | N/A |
| 4    | ETHUSDT | f1_sep\|f2_angle\|f3_d200 (27 estados) | Alerta close TradingView | SI (LIVE) | NO — TradingView gestiona |
| 5-10 | varios  | price_zone\|rr_level\|hour_zone (27)   | Price Poller (sl/tp)     | SI (LIVE) | SI — Binance monitorea    |

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
|                 bot_ejecutor  (FastAPI :8001)                  |
|                                                                |
|  FASE 1: Validacion                                            |
|    Verificar secret + IP + status="pending"                    |
|                                                                |
|  FASE 2: StrategyRegistry.get(strategy_id)                     |
|    "1"  -> Worker Estrategia 1  (SOLUSDT, 3D, 2 alertas, LIVE)|
|    "2"  -> Worker Estrategia 2  (SOLUSDT, 5D, 2 alertas, LEARN)|
|    "3"  -> Worker Estrategia 3  (SOLUSDT, 3D, 2 alertas, LEARN)|
|    "4"  -> Worker Estrategia 4  (ETHUSDT, 3D, 2 alertas, LIVE)|
|    "5"->"10" -> Worker Scaffold (3D, 1 alerta, LIVE)          |
|                                                                |
|  FASE 3: Routing por signal_type                               |
|    signal_type="open"  -> worker.decide() -> ejecutar/skip     |
|    signal_type="close" -> cierre inmediato (directo)           |
|                                                                |
|  FASE 4a: Apertura (signal_type="open")                        |
|    encode_state(params) -> estado del motor                    |
|    motor.choose_action(estado) [epsilon-greedy]                |
|    -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT              |
|    Si ejecuta:                                                 |
|      - LIVE: binance_executor.open_position()                  |
|        * balance disponible x 0.95 = margen                    |
|        * margen x leverage(25) = notional                      |
|        * MARKET entry + STOP_MARKET + TP_MARKET (solo 5-10)   |
|      - LEARN ONLY (2,3): simula sin tocar Binance              |
|      open_positions[(id, symbol)] = {state, action, ...}       |
|                                                                |
|  FASE 4b: Cierre (signal_type="close") [estrategias 1,2,3,4]  |
|    Recupera state/action de open_positions                     |
|    - LIVE: binance_executor.close_position(symbol)             |
|      * cancel_open_orders -> MARKET reduceOnly                 |
|    - LEARN ONLY: simula cierre sin tocar Binance               |
|    compute_reward(pnl_pct, duration_min)                       |
|    worker.update() -> actualizacion inmediata del motor        |
|    update_excel_result(WIN/LOSS, pnl_pct, pnl_notes)          |
|                                                                |
|  FASE 5: Persistencia (siempre)                                |
|    estrategias/{id}/trade_log.xlsx      <- resultado al cierre |
|    estrategias/{id}/actividades/        <- motor + logs        |
|    estrategias/{id}/INSIGHTS.md        <- resumen aprendizaje  |
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
|     2. margin = balance * 0.95                                 |
|     3. qty = (margin * 25) / price  [step size de Binance]    |
|     4. futures_change_leverage(symbol, 25)                     |
|     5. MARKET BUY/SELL qty                                     |
|     6. STOP_MARKET  (SOLO estrategias 5-10)                    |
|     7. TAKE_PROFIT_MARKET  (SOLO estrategias 5-10)             |
|     Estrategias 1,2,3,4: sl y tp = None (TradingView gestiona)|
|                                                                |
|   close_position(symbol):                                      |
|     1. futures_cancel_all_open_orders(symbol)                  |
|     2. get_position_qty(symbol)  -> qty real                   |
|     3. MARKET SELL/BUY qty reduceOnly=True                     |
+----------------------------------------------------------------+


PRICE POLLER (hilo independiente, cada 60 segundos):
Solo activo para estrategias 5-10.

+----------------------------------------------------------------+
|  manager/price_poller.py                                       |
|                                                                |
|  SELF_CLOSING = {"1","2","3","4"}  <- excluidas               |
|  Fuente: https://api.binance.com/api/v3/ticker/price           |
|  Sin API key, tiempo real                                      |
|                                                                |
|  Para cada posicion pendiente (5-10) con sl+tp:               |
|    BUY:  precio >= tp -> WIN  |  precio <= sl -> LOSS          |
|    SELL: precio <= tp -> WIN  |  precio >= sl -> LOSS          |
|    > 24h sin cierre   -> EXPIRED (LOSS)                        |
|                                                                |
|  Al detectar cierre:                                           |
|    worker.update(state, action, reward)                        |
|    update_excel_result(order_id, result, pnl_pct, pnl_notes)  |
+----------------------------------------------------------------+


ESTADO EN DISCO (por estrategia, id = 1 a 10):

  estrategias/estrategia_{id}/
    INSIGHTS.md                 resumen de aprendizaje del motor
    trade_log.xlsx              Excel de trades (result/pnl_pct al cierre)

  estrategias/estrategia_{id}/actividades/
    q_table.json                motor de decision (estados aprendidos)
    qlearning_stats.json        epsilon, alpha actuales
    replay_buffer.jsonl         historial de experiencias
    learning_journal.jsonl      registro detallado por actualizacion
    decision_log.jsonl          historial de decisiones tomadas
    events/                     reporte JSON por evento
    backups/                    snapshots automaticos cada 6h
```

---

## Configuracion activa (.env)

| Variable               | Valor | Descripcion                                                    |
|------------------------|-------|----------------------------------------------------------------|
| BINANCE_LEVERAGE       | 25    | Apalancamiento para todas las ordenes                          |
| BINANCE_MAX_MARGIN_PCT | 0.95  | 95% del balance por trade (0.99 causa "Margin is insufficient")|
| BINANCE_TESTNET        | false | Cuenta real de Binance                                         |
| DRY_RUN                | false | Operaciones reales                                             |
| POLL_INTERVAL_SEC      | 60    | Frecuencia del Price Poller                                    |

## Independencia de componentes

| Componente        | Depende de          | Comportamiento si cae                     |
|-------------------|---------------------|-------------------------------------------|
| bot_ejecutor      | Python, .env        | bot_ejecutor.bat lo reinicia en 5s        |
| binance_executor  | API key + internet  | Loguea error, no crashea el bot           |
| Price Poller      | API publica Binance | Reintenta en el siguiente ciclo (60s)     |
| Excel update      | openpyxl            | Warning en log, no crashea               |
| TradingView       | ngrok activo        | Solo afecta entrada de senales            |
