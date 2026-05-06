# Arquitectura de bot3-qlearning

Patron identico a bot2 (agente01). Capas de Research, Analysis, Decision y Sender.

## Diagrama de Componentes

```
+------------------------------------------------------------------+
|                          bot3.py                                 |
|              (FastAPI - puerto 8001 - event-driven)              |
|                                                                  |
|  Cada vez que TradingView dispara una alerta PineScript:         |
|                                                                  |
|  FASE 1: Validar envelope TV                                     |
|     a. Verificar X-Webhook-Secret (TV_WEBHOOK_SECRET)            |
|     b. Verificar IP si TV_ENFORCE_IP=true                        |
|     c. parse_tv_envelope() -> TVEnvelope validado                 |
|                                                                  |
|  FASE 2: Q-Learning Decision                                     |
|     a. state_encoder.encode_state() -> "regime|vol|momentum"      |
|     b. QLearningAgent.choose_action() (epsilon-greedy)           |
|     c. TVQLearningStrategy.decide()                              |
|        -> EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT             |
|                                                                  |
|  FASE 3: Envio a bot1 (patron identico a bot2)                   |
|     a. signal_formatter.build_payload() -> envelope bot1          |
|        strategy_id: "bot3_qlearning"                             |
|        source:      "bot3_qlearning_agent"                       |
|     b. webhook_client.send() -> POST /webhook/bot3                |
|        backoff: 5s -> 10s -> 15s (3 intentos)                      |
|        status="executed"  -> exito, track en pending_q_decisions  |
|        status="rejected"  -> log + Telegram *                    |
|        status="failed"    -> state/pending_signals.json           |
|                                                                  |
|  FASE 4: Persistencia (patron identico a bot2)                   |
|     a. _log_decision()       -> state/decision_log.jsonl          |
|     b. _write_event_report() -> logs/YYYY-MM-DD_HH-MM-SS.json    |
|     c. append_excel_rows()   -> logs/trade_log.xlsx               |
|     d. telegram_notifier.*() -> Telegram                          |
|                                                                  |
|  FASE 5: Hindsight Learning (POST /qlearning/update)             |
|     Cuando bot1 confirma cierre de posicion:                     |
|     a. compute_reward() -> formula: pnl_pct - slippage - penalty  |
|     b. agent.update() -> Bellman update Q(s,a)                    |
|     c. agent.decay_params() -> alpha y epsilon decaen             |
|     d. trainer.append_experience() -> replay_buffer.jsonl         |
|                                                                  |
+------------+-----------------------------------------------------+
             |
    +--------v----------------------------------------------+
    |                   SENDER LAYER                        |
    |              (patron identico a bot2)                 |
    |                                                       |
    |  sender/webhook_client.py                             |
    |  +- DRY_RUN=true  -> solo loguea, no envia             |
    |  +- POST a http://127.0.0.1:8000/webhook/bot3         |
    |  |   Header: X-Webhook-Secret (BOT1_WEBHOOK_SECRET)   |
    |  +- backoff: 5s -> 10s -> 15s (3 intentos)             |
    |  +- failed -> state/pending_signals.json               |
    |                                                       |
    |  sender/signal_formatter.py                           |
    |  +- build_payload() -> envelope compatible con bot1    |
    |  |   strategy_id: "bot3_qlearning"                    |
    |  |   source:      "bot3_qlearning_agent"              |
    |  +- build_no_signal_payload() -> informativo           |
    |                                                       |
    |  sender/telegram_notifier.py                          |
    |  +- signal_sent()     -> * ejecutado por bot1          |
    |  +- signal_rejected() -> * rechazado por bot1          |
    |  +- webhook_failed()  -> * fallo de red, en cola       |
    |  +- signal_skipped()  -> 🔍 Q-Learning descarto         |
    |  +- agent_paused()    -> 🛑 auto-pausa activada         |
    |  +- startup()         -> 🚀 bot3 arrancado              |
    +--------+----------------------------------------------+
             |
    +--------v----------------------------------------------+
    |                Q-LEARNING LAYER                       |
    |                                                       |
    |  core/qlearning_agent.py                              |
    |  +- Q-Table: 27 estados x 4 acciones                  |
    |  +- Epsilon-greedy: explora / explota                 |
    |  +- Bellman update al recibir reward                  |
    |  +- Auto-pause si win_rate < baseline * 0.7           |
    |  +- Persist: data/qlearning/q_table.json              |
    |                                                       |
    |  core/state_encoder.py                                |
    |  +- regime(3) x volatility(3) x momentum(3) = 27     |
    |                                                       |
    |  core/reward_calculator.py                            |
    |  +- r = pnl - slippage - duration_penalty + R_bonus  |
    |                                                       |
    |  manager/qlearning_trainer.py                         |
    |  +- replay_buffer.jsonl (historial de experiencias)   |
    |  +- Backups Q-table cada 6h (max 28)                  |
    +-------------------------------------------------------+

Estado en disco:
  state/decision_log.jsonl    - historial de todas las decisiones
  state/pending_signals.json  - senales en cola (retry automatico)
  data/qlearning/q_table.json - Q-table persistida
  logs/YYYY-MM-DD_HH-MM-SS.json - reporte por evento
  logs/trade_log.xlsx          - Excel acumulado
```
