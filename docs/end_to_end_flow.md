# Flujo End-to-End - bot3 Multi-Strategy

## Flujo completo: TradingView -> Q-Learning -> bot1 -> Alpaca -> aprendizaje automatico

```
+-------------------+
|   TradingView     |
|   .pine alert     |
+--------+----------+
         |
         |  POST http://<ngrok>/webhook/strategy/qlearning
         |  Header: X-Webhook-Secret: <TV_WEBHOOK_SECRET>
         |  Body: JSON envelope con strategy params (ver webhook_format.md)
         v
+-----------------------------------------------------------+
|              bot3.py -- localhost:8001                    |
|                                                           |
|  1. Verificar X-Webhook-Secret (401 si falla)             |
|  2. Verificar IP si TV_ENFORCE_IP=true (403 si falla)     |
|  3. Parsear envelope                                      |
|  4. Si status != "pending" -> 200 silente, no accion      |
|                                                           |
|  5. StrategyRegistry.get("qlearning")                     |
|     -> QLearningWorker                                    |
|                                                           |
|  +-----------------------------------------------------+  |
|  |  QLearningWorker.decide(body)                       |  |
|  |                                                     |  |
|  |  parse_signal(body):                                |  |
|  |    symbol="SOLUSDT", action="buy", params={...}     |  |
|  |                                                     |  |
|  |  encode_state(params):                              |  |
|  |    regime="trend_up", momentum="bullish"            |  |
|  |    setup_type="breakout", htf_bias="bull"           |  |
|  |    trend_strength="extreme"                         |  |
|  |    -> "trend_up|bullish|breakout|bull|extreme"      |  |
|  |                                                     |  |
|  |  agent.choose_action(state) [epsilon-greedy]:       |  |
|  |    70% explota -> accion con Q mas alto             |  |
|  |    30% explora -> accion aleatoria                  |  |
|  |    -> "EXECUTE_FULL"                                |  |
|  |                                                     |  |
|  |  EXECUTE_FULL  -> side=buy,   size*1.0, execute=T  |  |
|  |  EXECUTE_HALF  -> side=buy,   size*0.5, execute=T  |  |
|  |  SKIP          -> execute=False, retorna            |  |
|  |  INVERT        -> side=sell,  size*0.5, execute=T  |  |
|  +-----------------------------------------------------+  |
|                                                           |
|  6. Si execute=True:                                      |
|     webhook_client.send() -> POST /webhook/bot3           |
|     pending_q_decisions[order_id] = {                     |
|       strategy_id: "qlearning"                            |
|       state:   "trend_up|bullish|breakout|bull|extreme"   |
|       action:  "EXECUTE_FULL"                             |
|       symbol:  "SOLUSDT"                                  |
|       side:    "buy"                                      |
|       entry_price: 93.73                                  |
|       sl: 93.63, tp: 93.93                                |
|       open_time: <timestamp>                              |
|     }                                                     |
|                                                           |
|  7. Persistencia:                                         |
|     state/qlearning/decision_log.jsonl                    |
|     logs/qlearning/events/YYYY-MM-DD_HH-MM-SS.json        |
|     logs/qlearning/trade_log.xlsx                         |
+----------------------------+------------------------------+
                             |
                             v
+-----------------------------------------------------------+
|              bot1.py -- localhost:8000                    |
|  1. Valida BOT3_WEBHOOK_SECRET                            |
|  2. Valida IP (localhost only)                            |
|  3. Ejecuta en Alpaca                                     |
|  -> {"status": "executed", "order_id": "<uuid>"}          |
+-----------------------------------------------------------+
                             |
                             v
+-----------------------------------------------------------+
|              Alpaca API (live / paper)                    |
|  Orden ejecutada                                          |
+-----------------------------------------------------------+
```

---

## Flujo de aprendizaje automatico (Price Poller)

El Price Poller corre en un hilo separado, independiente del servidor web.
No requiere intervencion manual. Cierra el ciclo de aprendizaje solo.

```
+-----------------------------------------------------------+
|  manager/price_poller.py  (hilo daemon, cada 30s)         |
|                                                           |
|  Para cada entrada en pending_q_decisions:                |
|    Si no tiene entry_price/sl/tp -> saltar                |
|                                                           |
|    GET https://api.binance.com/api/v3/ticker/price        |
|        ?symbol=SOLUSDT                                    |
|    -> {"symbol":"SOLUSDT","price":"93.84"}                |
|                                                           |
|    Evaluar resultado:                                     |
|      buy:  precio >= tp -> TP HIT -> reward = +0.40       |
|            precio <= sl -> SL HIT -> reward = -0.40       |
|      sell: precio <= tp -> TP HIT -> reward = +0.40       |
|            precio >= sl -> SL HIT -> reward = -0.40       |
|      Si lleva > 24h sin cierre -> EXPIRED -> reward = 0   |
|                                                           |
|    Llamar worker.update_q(state, action, reward, s_next)  |
|    Remover de pending_q_decisions                         |
+----------------------------+------------------------------+
                             |
                             v
+-----------------------------------------------------------+
|  StrategyWorker.update_q()                                |
|                                                           |
|  old_q = agent.get_q_values(state).get(action, 0.0)      |
|  new_q = agent.update(state, action, reward, next_state)  |
|                                                           |
|  Bellman:                                                 |
|  Q(s,a) += alpha * [reward + gamma * max Q(s') - Q(s,a)] |
|                                                           |
|  agent.decay_params()                                     |
|    epsilon *= 0.999  (min 0.02)                           |
|    alpha   *= 0.999  (min 0.02)                           |
|                                                           |
|  trainer.append_experience(s, a, r, s_next)               |
|    -> data/strategies/qlearning/replay_buffer.jsonl       |
|                                                           |
|  trainer.save_and_backup()                                |
|    -> data/strategies/qlearning/q_table.json              |
|    -> data/strategies/qlearning/backups/                  |
|                                                           |
|  journal.record_update(state, action, reward, old_q, new_q)
|    Genera conclusion en texto:                            |
|    "Q sube de 0.000 a 0.040 tras trade ganador            |
|     (reward=+0.400). aprendiendo: datos insuficientes."   |
|                                                           |
|    -> logs/qlearning/learning_journal.jsonl               |
|    -> logs/qlearning/INSIGHTS.md  (sobreescrito)          |
+-----------------------------------------------------------+
```

---

## INSIGHTS.md - Ejemplo de lo que aprende el agente

Despues de suficientes trades, `logs/qlearning/INSIGHTS.md` contiene:

```
## Contextos RENTABLES (el agente prefiere ejecutar aqui)

| Estado                                    | Accion       | Q-value |
|-------------------------------------------|--------------|---------|
| trend_up|bullish|breakout|bull|extreme    | EXECUTE_FULL | +0.3842 |
| trend_up|bullish|trend|bull|strong        | EXECUTE_FULL | +0.2910 |

Sugerencia para TradingView:
Los mejores resultados ocurren cuando: trend_up + bullish + breakout + bull + extreme.
Considera priorizar alertas en este contexto.

## Contextos BLOQUEADOS (el agente descarta automaticamente)

| Estado                               | Accion evitada | Q-value |
|--------------------------------------|----------------|---------|
| range|bearish|pullback|bear|weak     | EXECUTE_FULL   | -0.4200 |

Filtros sugeridos para Pine Script:
- Evitar entradas cuando: range + bearish + pullback + bear + weak (Q=-0.4200)
```

---

## Aprendizaje manual (alternativo al Price Poller)

Si el activo no esta en Binance (SPY, acciones US) o quieres forzar aprendizaje:

```powershell
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    order_id              = "759b9684-528d-47cc-b54a-98aa68003a5a"
    pnl_pct              = 0.5
    duration_min         = 45.0
    account_drawdown_pct = -1.2
    r_multiple           = 1.5
    next_state           = "range|neutral|pullback|neutral|weak"
} | ConvertTo-Json

Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/update `
    -Method POST -Headers $headers -Body $body
```
