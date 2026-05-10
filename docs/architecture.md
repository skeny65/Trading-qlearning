# Arquitectura de bot3 - Multi-Strategy Q-Learning

## Estado: OPERATIVO (2026-05-09)

## Principio de diseno

Cada proceso es completamente independiente:
- Cada estrategia tiene su propia Q-table, agente, logs y Excel
- El Price Poller cierra el ciclo de aprendizaje sin intervencion humana
- El Excel se llena automaticamente con WIN/LOSS cuando cierra cada posicion
- bot1 es opcional: el bot funciona y aprende sin el

## Diagrama de Componentes

```
+----------------------------------------------------------------+
|                  TradingView PineScript                        |
|  POST http://<ngrok>/webhook/strategy/{id}                     |
|  Header: X-Webhook-Secret                                      |
+------------------------+---------------------------------------+
                         |
                         v
+----------------------------------------------------------------+
|                    bot3.py  (FastAPI :8001)                    |
|                                                                |
|  FASE 1: Validacion                                            |
|    Verificar X-Webhook-Secret + IP + status="pending"          |
|                                                                |
|  FASE 2: StrategyRegistry.get(strategy_id)                     |
|    "apuesta"   -> ApuestaWorker    (state 3D: 27 estados)      |
|    "qlearning" -> QLearningWorker  (state 5D: 243 estados)     |
|    "tanque"    -> TanqueWorker     (state 3D: 27 estados)      |
|                                                                |
|  FASE 3: worker.decide(body)                                   |
|    parse_signal -> encode_state -> agent.choose_action         |
|    -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT              |
|                                                                |
|  FASE 4: Persistencia (siempre, con o sin bot1)                |
|    logs/{id}/trade_log.xlsx  <- fila nueva (result=VACIO)      |
|    state/{id}/decision_log.jsonl                               |
|    logs/{id}/events/YYYY-MM-DD_HH-MM-SS.json                  |
|                                                                |
|  FASE 5: Envio a bot1 (background, opcional)                   |
|    webhook_client.send() -> POST /webhook/bot3                 |
|    pending_q_decisions[order_id] = {                           |
|      strategy_id, state, action,                               |
|      entry_price, sl, tp, symbol, side, open_time             |
|    }  <- se registra incluso si bot1 esta caido                |
+----------------------------------------------------------------+
                         |
          (opcional, si bot1 esta corriendo)
                         v
+----------------------------------------------------------------+
|   bot1.py  (FastAPI :8000) -> Alpaca API                      |
+----------------------------------------------------------------+


PRICE POLLER (hilo independiente, cada 60 segundos):

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
|      -> Abre trade_log.xlsx                                    |
|      -> Busca fila por order_id                                |
|      -> Escribe result=WIN/LOSS, pnl_notes, learned_at         |
|      -> Guarda Excel                                           |
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


ESTADO EN DISCO (por estrategia):

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

| Componente | Depende de | Falla si cae |
|------------|------------|-------------|
| bot3 | Python, .env | Se reinicia solo (start_bot3.bat) |
| Price Poller | Binance API publica | Reintenta cada 60s |
| Excel update | openpyxl | Log warning, no crashea |
| bot1 | Alpaca | bot3 sigue funcionando y aprendiendo |
| TradingView | ngrok | Solo afecta la entrada de senales |

## Nota importante

El `.env` de bot3 no tiene `ALPACA_API_KEY`. No conecta directo con Alpaca.
El Price Poller usa solo la API PUBLICA de Binance (sin credenciales).
