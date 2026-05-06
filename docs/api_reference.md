# API Reference - bot3-qlearning

Base URL: `http://localhost:8001`

## Endpoints existentes

### `GET /`
Health check rapido.

### `GET /health`
Estado detallado: dry_run, paused, epsilon, alpha, pending_decisions.

---

## Endpoint nuevo: TradingView Webhook

### `POST /webhook/tv`

Recibe alertas de TradingView y las procesa con el agente Q-Learning.

**Headers requeridos:**
```
Content-Type:    application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

**Body:** ver `docs/webhook_format.md`

**Respuestas:**

| HTTP | status                   | Significado                                      |
|------|--------------------------|--------------------------------------------------|
| 200  | executed / executed_dry_run | Q-Learning eligio EXECUTE_FULL o HALF         |
| 200  | skipped_by_qlearning     | Q-Learning decidio SKIP                          |
| 200  | inverted_by_qlearning    | Q-Learning ejecuto la operacion contraria         |
| 200  | rejected                 | Agente pausado                                   |
| 200  | received_no_signal_tv    | status != "pending", no se tomo accion           |
| 400  | -                        | JSON invalido                                    |
| 401  | -                        | X-Webhook-Secret incorrecto                      |
| 403  | -                        | IP no permitida (si TV_ENFORCE_IP_WHITELIST=true)|
| 422  | -                        | Campos faltantes o invalidos en el envelope      |

---

## Endpoints Q-Learning

### `GET /qlearning/status`
Resumen del agente: alpha, epsilon, paused, best/worst state-action, recent rewards.

### `GET /qlearning/qtable`
Q-table completa en JSON.

### `POST /qlearning/update`
Aplica aprendizaje hindsight cuando una posicion se cierra.

**Body:**
```json
{
  "order_id":              "dry_SPY_20260503_143000000000",
  "pnl_pct":              1.25,
  "duration_min":         45.0,
  "account_drawdown_pct": -2.5,
  "r_multiple":           2.1,
  "next_state":           "range|mid|neutral"
}
```

### `POST /qlearning/pause`  /  `POST /qlearning/resume`
Pausa o reactiva el agente manualmente.

### `GET /pending`
Decisiones pendientes de cierre de posicion.
