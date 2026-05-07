# Q-Learning Strategy - bot3

## Filosofia

El agente Q-Learning aprende a filtrar y modificar senales de TradingView para
maximizar el rendimiento a largo plazo. En lugar de ejecutar ciegamente cada
alerta, el agente decide la accion optima basandose en el estado del mercado
(regimen + volatilidad + momentum) y su experiencia acumulada.

## Estados (s) - 27 combinaciones

| Dimension  | Valores                              | Origen en PineScript           |
|------------|--------------------------------------|--------------------------------|
| regime     | trend_up \| trend_down \| range      | ADX + EMA fast/slow crossover  |
| volatility | low \| mid \| high                   | ATR percentil (30/70) 100 velas|
| momentum   | bullish \| bearish \| neutral        | RSI(14) thresholds 45/55       |

**Clave:** `"trend_up|mid|bullish"`

## Acciones (a)

| Accion        | Comportamiento                                          |
|---------------|---------------------------------------------------------|
| EXECUTE_FULL  | Tomar la senal con el size recibido (x1.0)              |
| EXECUTE_HALF  | Tomar la senal con size * 0.5                           |
| SKIP          | No ejecutar - responde `skipped_by_qlearning`           |
| INVERT        | Ejecutar la operacion contraria con size * 0.5          |

## Recompensa (r)

```
r  = pnl_pct
r -= 0.05                       # comision + slippage
r -= 0.10  si duracion > 4h
r -= 0.50  si drawdown_cuenta < -10%
r += 0.20  si pnl_pct > 0 y r_multiple >= 2
```

## Actualizacion Q-Table (Bellman)

```
Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]
```

## Hiperparametros iniciales

| Parametro           | Valor | Min  | Decay       |
|---------------------|-------|------|-------------|
| alpha (learning)    | 0.10  | 0.02 | x0.999/trade|
| gamma (descuento)   | 0.90  | -    | fijo        |
| epsilon (exploracion)| 0.20 | 0.02 | x0.999/trade|

## Auto-pausa por degradacion

Cada 20 trades se evalua la ventana movil:
- Si `win_rate_reciente < win_rate_baseline * 0.70` el agente se auto-pausa.
- Se notifica por Telegram (si esta configurado).
- Se puede reactivar via `POST /qlearning/resume`.

## Flujo completo

```
TradingView alert
    |
    v
POST /webhook/tv  (X-Webhook-Secret header)
    |
    +--> parse_tv_envelope()
    +--> encode_state(regime, volatility, momentum)
    +--> agent.choose_action(state)   [epsilon-greedy]
    |
    +-- EXECUTE_FULL  -> webhook_client.send() -> bot1 -> Alpaca (size x1.0)
    +-- EXECUTE_HALF  -> webhook_client.send() -> bot1 -> Alpaca (size x0.5)
    +-- SKIP          -> log + return skipped_by_qlearning
    +-- INVERT        -> webhook_client.send() -> bot1 -> Alpaca (side invertido, x0.5)
    |
    v
pending_q_decisions[order_id] = {state, action, timestamp}
    |
    v  (cuando la posicion se cierra - manual o TP/SL)
POST /qlearning/update  {order_id, pnl_pct, duration_min, ...}
    |
    +--> compute_reward(trade_result)
    +--> agent.update(s, a, r, s_next)
    +--> agent.decay_params()
    +--> trainer.append_experience(...)
    +--> agent.save()
```

## Enviar actualizacion de aprendizaje (PowerShell)

Cuando cierra una posicion, enviar el resultado a bot3 para que aprenda:

```powershell
$headers = @{ "Content-Type" = "application/json" }
$body = @{
    order_id              = "759b9684-528d-47cc-b54a-98aa68003a5a"
    pnl_pct              = 0.5
    duration_min         = 45.0
    account_drawdown_pct = -1.2
    r_multiple           = 1.5
    next_state           = "range|mid|neutral"
} | ConvertTo-Json

Invoke-WebRequest -Uri http://localhost:8001/qlearning/update `
    -Method POST -Headers $headers -Body $body
```

## Monitoreo

```powershell
# Resumen del agente: alpha, epsilon, paused, best/worst state-action
Invoke-WebRequest http://localhost:8001/qlearning/status | Select-Object -ExpandProperty Content

# Q-table completa
Invoke-WebRequest http://localhost:8001/qlearning/qtable | Select-Object -ExpandProperty Content

# Decisiones pendientes de cierre
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

## Intervencion manual

```powershell
# Pausar agente
Invoke-WebRequest -Uri http://localhost:8001/qlearning/pause -Method POST

# Reanudar agente
Invoke-WebRequest -Uri http://localhost:8001/qlearning/resume -Method POST

# Restaurar Q-Table desde backup
Copy-Item "data\qlearning\backups\q_table_20260506_060000.json" "data\qlearning\q_table.json"

# Resetear Q-Table (tabla vacia)
'{}' | Out-File data\qlearning\q_table.json -Encoding utf8
```
