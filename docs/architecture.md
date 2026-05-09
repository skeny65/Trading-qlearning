# Arquitectura de bot3 - Multi-Strategy Q-Learning

## Estado: OPERATIVO (2026-05-06)

## Principio de diseno

Cada proceso es completamente independiente. Cada estrategia tiene:
- Su propia Q-table (datos separados en disco)
- Su propio agente Q-Learning (epsilon y alpha independientes)
- Su propio diario de aprendizaje (INSIGHTS.md exclusivo)
- Sus propios logs (Excel, JSONL, reportes de eventos)

El aprendizaje se cierra automaticamente via Price Poller sin intervenci n manual.

## Diagrama de Componentes

```
+----------------------------------------------------------------+
|                  TradingView PineScript                        |
|  Alerta configurada con:                                       |
|    URL: http://<ngrok>/webhook/strategy/{id}                   |
|    Secret: TV_WEBHOOK_SECRET                                   |
+------------------------+---------------------------------------+
                         |
                         |  POST /webhook/strategy/{id}
                         |  Header: X-Webhook-Secret
                         v
+----------------------------------------------------------------+
|                    bot3.py  (FastAPI :8001)                    |
|                                                                |
|  FASE 1: Validacion                                            |
|    - Verificar X-Webhook-Secret                                |
|    - Verificar IP si TV_ENFORCE_IP_WHITELIST=true              |
|    - status != "pending" -> ignorar silenciosamente            |
|                                                                |
|  FASE 2: StrategyRegistry.get(strategy_id)                     |
|    +--------------------------------------------------+        |
|    |  StrategyRegistry (singleton)                    |        |
|    |    "apuesta"   -> ApuestaWorker                  |        |
|    |    "qlearning" -> QLearningWorker                |        |
|    |    "tanque"    -> TanqueWorker                   |        |
|    +--------------------------------------------------+        |
|                                                                |
|  FASE 3: worker.decide(body)                                   |
|    worker.parse_signal(body) -> symbol, action, params         |
|    worker.encode_state(params) -> estado string                |
|    agent.choose_action(state) -> epsilon-greedy                |
|    -> EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT              |
|                                                                |
|  FASE 4: Envio a bot1 (si execute=True)                        |
|    webhook_client.send() -> POST http://127.0.0.1:8000         |
|                             /webhook/bot3                       |
|    pending_q_decisions[order_id] = {                           |
|      strategy_id, state, action,                               |
|      entry_price, sl, tp, symbol, side, open_time             |
|    }                                                           |
|                                                                |
|  FASE 5: Persistencia por estrategia                           |
|    _log_decision()      -> state/{id}/decision_log.jsonl       |
|    _write_event_report()-> logs/{id}/events/YYYY-MM-DD_*.json  |
|    append_excel_rows()  -> logs/{id}/trade_log.xlsx            |
|    telegram_notifier.*() -> Telegram                           |
|                                                                |
+------------------------+---------------------------------------+
                         |
                         | POST http://127.0.0.1:8000/webhook/bot3
                         v
+----------------------------------------------------------------+
|               bot1.py  (FastAPI :8000)                        |
|    1. Valida BOT3_WEBHOOK_SECRET                               |
|    2. Valida IP (localhost only)                               |
|    3. Verifica "bot3_qlearning" en KNOWN_BOTS                  |
|    4. Ejecuta orden en Alpaca                                  |
|    5. Retorna {"status":"executed", "order_id":"uuid"}         |
+------------------------+---------------------------------------+
                         |
                         v
+----------------------------------------------------------------+
|                  Alpaca API (Live / Paper)                     |
+----------------------------------------------------------------+


PRICE POLLER (hilo independiente):

+----------------------------------------------------------------+
|  manager/price_poller.py                                       |
|                                                                |
|  Intervalo: 30 segundos                                        |
|  Fuente: https://api.binance.com/api/v3/ticker/price           |
|                                                                |
|  Para cada pending_q_decisions con entry_price + sl + tp:      |
|    GET Binance precio actual                                    |
|    Si buy:  precio >= tp -> TP HIT (reward positivo)           |
|             precio <= sl -> SL HIT (reward negativo)           |
|    Si sell: precio <= tp -> TP HIT                             |
|             precio >= sl -> SL HIT                             |
|    Si > 24h sin cierre  -> expirar (reward neutro)             |
|                                                                |
|  Al detectar cierre:                                           |
|    registry.get(strategy_id).update_q(state, action, reward)   |
|    journal.record_update() -> INSIGHTS.md actualizado          |
+----------------------------------------------------------------+


LEARNING LAYER (por estrategia):

+----------------------------------------------------------------+
|  core/strategy_worker.py (clase base abstracta)                |
|                                                                |
|  Cada worker tiene instancias propias de:                      |
|    QLearningAgent(data_dir="data/strategies/{id}")             |
|    QLearningTrainer(agent, data_dir="data/strategies/{id}")    |
|    LearningJournal(strategy_id)                                |
|                                                                |
|  worker.update_q(state, action, reward, next_state):           |
|    agent.update() -> Bellman: Q(s,a) += alpha*[r+gamma*maxQ'] |
|    agent.decay_params() -> epsilon y alpha decaen              |
|    trainer.append_experience() -> replay_buffer.jsonl          |
|    trainer.save_and_backup() -> q_table.json + backup          |
|    journal.record_update() -> learning_journal.jsonl           |
|                           -> INSIGHTS.md (sobreescrito)        |
+----------------------------------------------------------------+


ESTADO EN DISCO:

  data/strategies/{id}/
    q_table.json             Q-Table persistida
    qlearning_stats.json     alpha, epsilon, gamma actuales
    replay_buffer.jsonl      historial de experiencias (s,a,r,s')
    backups/                 snapshots automaticos (max 28)

  state/{id}/
    decision_log.jsonl       historial de todas las decisiones

  logs/{id}/
    INSIGHTS.md              resumen de aprendizaje (siempre actualizado)
    learning_journal.jsonl   registro detallado por Q-update
    trade_log.xlsx           Excel acumulado
    events/                  reporte JSON por evento
```

## Nota importante

Bot3 NO conecta directamente con Alpaca. Toda ejecucion pasa a traves de bot1.
El `.env` de bot3 no tiene `ALPACA_API_KEY` ni `ALPACA_SECRET_KEY`.
El Price Poller usa solo la API PUBLICA de Binance (no requiere credenciales).
