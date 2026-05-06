# End-to-End Flow - Bot3 Q-Learning

## Flujo completo: TradingView -> Q-Learning -> Alpaca

```
+-----------------+
|   TradingView   |
|   .pine alert   |
|  (EMA/ATR/RSI)  |
+--------+--------+
         |  POST /webhook/tv
         |  Header: X-Webhook-Secret
         |  Body: JSON envelope con regime, volatility, momentum
         v
+--------------------------------------------+
|               bot.py (FastAPI)             |
|                                            |
|  1. Validar secret (401 si falla)          |
|  2. Validar IP si TV_ENFORCE_IP=true (403) |
|  3. Parsear envelope (422 si invalido)     |
|  4. Si status != "pending" -> 200 silente  |
|                                            |
|  +--------------------------------------+  |
|  |       tv_signal_parser               |  |
|  |  parse_tv_envelope(body) -> TVEnvelope| |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |       state_encoder                  |  |
|  |  encode_state(params)                |  |
|  |  -> "trend_up|mid|bullish"           |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |       QLearningAgent (epsilon-greedy)|  |
|  |  choose_action(state)                |  |
|  |  -> EXECUTE_FULL / HALF / SKIP /     |  |
|  |     INVERT                           |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |  TVQLearningStrategy.decide()        |  |
|  |  Aplica la accion:                   |  |
|  |   SKIP   -> return skipped (no trade)|  |
|  |   HALF   -> size *= 0.5              |  |
|  |   INVERT -> flip buy<->sell, *0.5    |  |
|  |   FULL   -> size sin cambio          |  |
|  +--------------+-----------------------+  |
|                 | (si execute=True)         |
|  +--------------v-----------------------+  |
|  |  OrderRouter (DRY_RUN o Alpaca live) |  |
|  |  Genera order_id                     |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  pending_q_decisions[order_id] = {state, action, ts}
|                                            |
+--------------------------------------------+
         |
         |  Respuesta HTTP 200
         v
+---------------------------------------------+
|  {                                          |
|    "status": "executed" | "skipped_by_ql"  |
|    "order_id": "dry_SPY_...",               |
|    "ql_action": "EXECUTE_FULL",             |
|    "state": "trend_up|mid|bullish",         |
|    "q_value": 0.1234,                       |
|    ...                                      |
|  }                                          |
+---------------------------------------------+

**********************************************

## Flujo de aprendizaje: posicion cerrada

Cuando una posicion se cierra (TP, SL, o manual):

  POST /qlearning/update
  {order_id, pnl_pct, duration_min, account_drawdown_pct, r_multiple, next_state}
         |
         v
  compute_reward(trade_result)
         |
         v
  agent.update(s, a, r, s_next)
  Q(s,a) <- Q(s,a) + alpha * [r + gamma * max Q(s_next,.) - Q(s,a)]
         |
         v
  agent.decay_params()   # alpha *= 0.999, epsilon *= 0.999
         |
         v
  agent.check_degradation()  # auto-pausa si WR < baseline * 0.7
         |
         v
  trainer.append_experience() -> replay_buffer.jsonl
         |
         v
  agent.save() -> q_table.json + qlearning_stats.json

**********************************************

## Flujo nocturno (reentrenamiento offline)

  DailyRunner.run() (10:00 AM configurado via APScheduler)
         |
         v
  QLearningTrainer.train_from_replay(epochs=3)
         |  Lee replay_buffer.jsonl
         |  Shuffle + 3 passes de actualizaciones Bellman
         |  Decay adicional de alpha y epsilon
         v
  agent.save()
  trainer.backup_qtable()
         |
         v
  dashboard/generate_dashboard.py  (con seccion Q-Learning Insights)
