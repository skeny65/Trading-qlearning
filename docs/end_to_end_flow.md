# Flujo End-to-End — bot3-qlearning

## Flujo completo: TradingView -> Q-Learning -> bot1 -> Alpaca

```
+-----------------+
|   TradingView   |
|   .pine alert   |  (o curl/PowerShell en tests manuales)
+--------+--------+
         |
         |  POST http://<ngrok>/webhook/tv          (produccion)
         |  POST http://localhost:8001/webhook/tv    (tests locales)
         |  Header: X-Webhook-Secret: <TV_WEBHOOK_SECRET>
         |  Body: JSON envelope con regime, volatility, momentum
         v
+--------------------------------------------+
|          bot3.py — localhost:8001          |
|                                            |
|  1. Validar TV_WEBHOOK_SECRET (401)        |
|  2. Validar IP si TV_ENFORCE_IP=true (403) |
|  3. Parsear envelope (422 si invalido)     |
|  4. Si status != "pending" -> 200 silente  |
|                                            |
|  +--------------------------------------+  |
|  |       tv_signal_parser               |  |
|  |  parse_tv_envelope() -> TVEnvelope   |  |
|  +----------------+---------------------+  |
|                   |                        |
|  +----------------v---------------------+  |
|  |       state_encoder                  |  |
|  |  regime x volatility x momentum      |  |
|  |  -> "trend_up|mid|bullish" (27 est.) |  |
|  +----------------+---------------------+  |
|                   |                        |
|  +----------------v---------------------+  |
|  |       QLearningAgent (epsilon-greedy)|  |
|  |  choose_action(state) ->             |  |
|  |    EXECUTE_FULL / EXECUTE_HALF /     |  |
|  |    SKIP / INVERT                     |  |
|  +----------------+---------------------+  |
|                   |                        |
|  +----------------v---------------------+  |
|  |     TVQLearningStrategy.decide()     |  |
|  |  SKIP   -> return, no sigue          |  |
|  |  HALF   -> size *= 0.5              |  |
|  |  INVERT -> flip buy<->sell, *0.5    |  |
|  |  FULL   -> size sin cambio          |  |
|  +----------------+---------------------+  |
|                   | (si execute=True)      |
|  +----------------v---------------------+  |
|  |     webhook_client.send()            |  |
|  |  POST http://127.0.0.1:8000          |  |
|  |       /webhook/bot3                  |  |
|  |  Header: X-Webhook-Secret:           |  |
|  |          <BOT1_WEBHOOK_SECRET>       |  |
|  |  Backoff: 5s -> 10s -> 15s          |  |
|  +----------------+---------------------+  |
|                   |                        |
|  pending_q_decisions[order_id] = {state, action}
|                                            |
+--------------------------------------------+
         |
         v (conexion localhost, < 1ms)
+--------------------------------------------+
|          bot1.py — localhost:8000          |
|                                            |
|  POST /webhook/bot3                        |
|  1. Valida BOT3_WEBHOOK_SECRET             |
|  2. Valida IP (localhost only)             |
|  3. Verifica bot3_qlearning en KNOWN_BOTS  |
|  4. Ejecuta orden en Alpaca                |
|  5. Loguea en data/bot3_decisions.jsonl    |
|  -> {"status": "executed", "order_id": UUID}
|                                            |
+--------------------------------------------+
         |
         v
+--------------------------------------------+
|           Alpaca API (live / paper)        |
|  Orden ejecutada                           |
|  order_id: 759b9684-528d-47cc-b54a-...    |  <- confirmado 2026-05-06
+--------------------------------------------+

bot3 guarda en state/decision_log.jsonl:
  {event_id, ql_action, state, symbol, size, order_id, ...}

bot3 guarda en logs/YYYY-MM-DD_HH-MM-SS.json:
  reporte completo por evento
```

---

## Flujo de aprendizaje: cierre de posicion

Cuando la posicion cierra (TP, SL, o manual), enviar a bot3:

```
POST http://localhost:8001/qlearning/update
{
  "order_id":              "759b9684-528d-47cc-b54a-98aa68003a5a",
  "pnl_pct":              0.5,
  "duration_min":         45.0,
  "account_drawdown_pct": -1.2,
  "r_multiple":           1.5,
  "next_state":           "range|mid|neutral"   (opcional)
}
         |
         v
  compute_reward(trade_result)
  r = pnl_pct - 0.05 (slippage) [- penalizaciones] [+ bonus R]
         |
         v
  agent.update(s, a, r, s_next)
  Q(s,a) <- Q(s,a) + alpha * [r + gamma * max Q(s_next) - Q(s,a)]
         |
         v
  agent.decay_params()     # alpha *= 0.999, epsilon *= 0.999
  agent.check_degradation() # auto-pausa si WR < baseline * 0.7
         |
         v
  trainer.append_experience() -> data/qlearning/replay_buffer.jsonl
  agent.save()             -> data/qlearning/q_table.json
```

---

## Respuesta de bot3 al webhook de TradingView

```json
{
  "ticker":          "SPY",
  "original_action": "buy",
  "ql_action":       "EXECUTE_FULL",
  "state":           "trend_up|mid|bullish",
  "q_value":         0.0,
  "execute":         true,
  "side":            "buy",
  "size":            0.1,
  "status":          "executed",
  "order_id":        "759b9684-528d-47cc-b54a-98aa68003a5a",
  "dry_run":         false,
  "reason":          "Q-Learning: execute full position",
  "timestamp":       "2026-05-06T21:17:39.517354+00:00"
}
```

---

## Flujo nocturno (reentrenamiento offline)

```
QLearningTrainer.train_from_replay(epochs=3)
  Lee replay_buffer.jsonl completo
  Shuffle + 3 passes Bellman update
  Decay adicional de alpha y epsilon
  agent.save()
  trainer.backup_qtable() -> data/qlearning/backups/q_table_YYYYMMDD_HHMMSS.json
```
