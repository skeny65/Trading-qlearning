# Arquitectura de bot3 - Multi-Strategy Q-Learning

## Estado: OPERATIVO (2026-05-16)

## Principio de diseno

Cada estrategia es completamente independiente:
- Cada una tiene su propia Q-table, agente, logs y Excel
- Las estrategias 1 y 2 usan flujo de **2 alertas** (open + close desde TradingView)
- Las estrategias 3-10 usan flujo de **1 alerta** + Price Poller para detectar el cierre
- bot1 es opcional: el bot funciona y aprende sin el

## Estrategias registradas

| ID | Nombre     | Estado Q              | Flujo de cierre          |
|----|------------|-----------------------|--------------------------|
| 1  | Apuesta    | 3D: f1\|f2\|f3 (27)   | Alerta close TradingView |
| 2  | QLearning  | 5D: 5 dims (243)      | Alerta close TradingView |
| 3  | Tanque     | 3D: fuerza\|zona\|patron (27) | Price Poller (sl/tp) |
| 4-10 | Scaffold | 3D: precio\|rr\|hora (27) | Price Poller (sl/tp) |

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
|    "1"  -> ApuestaWorker    (state 3D, flujo 2 alertas)        |
|    "2"  -> QLearningWorker  (state 5D, flujo 2 alertas)        |
|    "3"  -> TanqueWorker     (state 3D, flujo 1 alerta)         |
|    "4"->"10" -> ScaffoldWorker (state 3D, flujo 1 alerta)      |
|                                                                |
|  FASE 3: Routing por signal_type                               |
|    signal_type="open"  -> worker.decide() (Q-Learning)         |
|    signal_type="close" -> cierre inmediato (bypass Q)          |
|                                                                |
|  FASE 3a: Apertura (signal_type="open")                        |
|    parse_signal -> encode_state -> agent.choose_action         |
|    -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT              |
|    Si ejecuta: open_positions[(id, symbol)] = {state, action}  |
|                                                                |
|  FASE 3b: Cierre (signal_type="close") [solo estrategias 1,2] |
|    Recupera state/action de open_positions                     |
|    -> Cierra posicion en bot1                                  |
|    -> update_q(state, action, reward) inmediato                |
|    -> update_excel_result(order_id, WIN/LOSS) inmediato        |
|                                                                |
|  FASE 4: Persistencia (siempre, con o sin bot1)                |
|    logs/{id}/trade_log.xlsx  <- fila nueva                     |
|    state/{id}/decision_log.jsonl                               |
|    logs/{id}/events/YYYY-MM-DD_HH-MM-SS.json                  |
|                                                                |
|  FASE 5: Envio a bot1 (background, opcional)                   |
|    webhook_client.send() -> POST /webhook/bot3                 |
|    pending_q_decisions[order_id] = {                           |
|      strategy_id, state, action,                               |
|      entry_price, sl, tp, symbol, side, open_time              |
|    }                                                           |
+----------------------------------------------------------------+
                         |
          (opcional, si bot1 esta corriendo)
                         v
+----------------------------------------------------------------+
|   bot1.py  (FastAPI :8000) -> Alpaca API                       |
+----------------------------------------------------------------+


PRICE POLLER (hilo independiente, cada 60 segundos):
Solo activo para estrategias con sl/tp en el payload (3-10).
Estrategias 1 y 2 aprenden por alerta de cierre, no por Price Poller.

+----------------------------------------------------------------+
|  manager/price_poller.py                                       |
|                                                                |
|  Fuente: https://api.binance.com/api/v3/ticker/price           |
|  Sin API key, gratuito, tiempo real                            |
|                                                                |
|  Para cada pending con entry_price + sl + tp:                  |
|    BUY:  precio >= tp -> WIN | precio <= sl -> LOSS            |
|    SELL: precio <= tp -> WIN | precio >= sl -> LOSS            |
|    > 24h -> EXPIRED -> LOSS                                    |
|                                                                |
|  Al cierre:                                                    |
|    worker.update_q(state, action, reward)                      |
|      -> Q-table actualizada (Bellman)                          |
|      -> replay_buffer.jsonl actualizado                        |
|      -> INSIGHTS.md regenerado                                 |
|                                                                |
|    update_excel_result(order_id, result, pnl_notes)            |
|      -> Abre logs/{id}/trade_log.xlsx                          |
|      -> Busca fila por order_id                                |
|      -> Escribe result=WIN/LOSS, pnl_notes, learned_at         |
+----------------------------------------------------------------+


CIERRE INMEDIATO (estrategias 1 y 2 via alerta TradingView):

+----------------------------------------------------------------+
|  Alerta close llega -> _send_close_to_bot1()                   |
|                                                                |
|  1. Envia orden de cierre a bot1                               |
|  2. Calcula duracion desde open_positions[(id, symbol)]        |
|  3. compute_reward(pnl_pct, duration_min)                      |
|  4. worker.update_q() -> Q-table actualizada al instante       |
|  5. update_excel_result() -> WIN/LOSS en Excel al instante     |
|  6. Elimina de pending_q_decisions y open_positions            |
+----------------------------------------------------------------+


LEARNING LAYER (por estrategia, completamente aislado):

+----------------------------------------------------------------+
|  core/strategy_worker.py (clase base abstracta)                |
|                                                                |
|  Cada worker instancia:                                        |
|    QLearningAgent(data_dir="data/strategies/{id}")             |
|    QLearningTrainer(agent, data_dir="data/strategies/{id}")    |
|    LearningJournal(strategy_id)                                |
+----------------------------------------------------------------+


ESTADO EN DISCO (por estrategia, id = 1 a 10):

  data/strategies/{id}/
    q_table.json             Q-Table persistida (aprende con cada trade)
    qlearning_stats.json     epsilon, alpha actuales
    replay_buffer.jsonl      historial de experiencias
    backups/                 snapshots automaticos

  state/{id}/
    decision_log.jsonl       historial de decisiones

  logs/{id}/
    trade_log.xlsx           Excel con result/pnl_notes llenados automaticamente
    INSIGHTS.md              resumen de aprendizaje (siempre actualizado)
    learning_journal.jsonl   registro detallado por Q-update
    events/                  reporte JSON por evento
```

## Independencia de componentes

| Componente      | Depende de             | Falla si cae                          |
|-----------------|------------------------|---------------------------------------|
| bot3            | Python, .env           | Se reinicia solo (start_bot3.bat)     |
| Price Poller    | Binance API publica    | Reintenta cada 60s                    |
| Cierre inmediato| Alerta TradingView     | Sin alerta = sin aprendizaje (1 y 2)  |
| Excel update    | openpyxl               | Log warning, no crashea               |
| bot1            | Alpaca                 | bot3 sigue funcionando y aprendiendo  |
| TradingView     | ngrok                  | Solo afecta la entrada de senales     |

## Nota importante

El `.env` de bot3 no tiene `ALPACA_API_KEY`. No conecta directo con Alpaca.
El Price Poller usa solo la API PUBLICA de Binance (sin credenciales).
