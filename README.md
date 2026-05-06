# Bot3 - Q-Learning Trading Bot

Trading bot que recibe alertas de **TradingView** (PineScript) y usa un agente
**Q-Learning** para decidir autonomamente si ejecutar, reducir, ignorar o invertir
cada senal. Aprende de cada operacion y mejora con el tiempo.

## Arquitectura

```
TradingView (.pine) --> POST /webhook/tv --> QLearningAgent --> Alpaca API
                                                   |
                                           Q-Table (persist)
                                           replay_buffer.jsonl
                                           auto-pausa por degradacion
```

## Canales de senal

| Canal            | Endpoint         | Descripcion                              |
|------------------|------------------|------------------------------------------|
| TradingView      | /webhook/tv      | Alertas EMA/ATR/RSI con Q-Learning       |

## Setup rapido

```bash
# 1. Crear estructura del proyecto (solo la primera vez)
python setup_project.py

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar entorno
copy .env.example .env
# editar .env con tus keys

# 4. Arrancar el bot
python bot.py

# 5. Verificar
curl http://localhost:8001/health

# 6. Tests
pytest tests/ -v
```

## Endpoints principales

| Metodo | Endpoint              | Descripcion                              |
|--------|-----------------------|------------------------------------------|
| GET    | /                     | Health check rapido                      |
| GET    | /health               | Estado detallado (mode, agent, pending)  |
| POST   | /webhook/tv           | Recibir alertas de TradingView           |
| GET    | /qlearning/status     | Alpha, epsilon, best/worst state-action  |
| GET    | /qlearning/qtable     | Q-table completa en JSON                 |
| POST   | /qlearning/update     | Aprendizaje cuando cierra una posicion   |
| POST   | /qlearning/pause      | Pausar agente manualmente                |
| POST   | /qlearning/resume     | Reanudar agente manualmente              |
| GET    | /pending              | Decisiones pendientes de cierre          |

## Testear manualmente (PowerShell)

```powershell
# Enviar senal de prueba
$env:TV_WEBHOOK_SECRET = "mi_secreto"
.\scripts\send_tv_signal.ps1

# O con curl
curl -X POST http://localhost:8001/webhook/tv `
  -H "Content-Type: application/json" `
  -H "X-Webhook-Secret: mi_secreto" `
  -d (Get-Content tests/fixtures/tv_envelope_buy.json -Raw)
```

## Estructura del proyecto

```
bot.py                              FastAPI entrypoint + todos los endpoints
core/
  qlearning_agent.py               Q-Table, epsilon-greedy, Bellman update
  state_encoder.py                 regime|volatility|momentum -> estado string
  reward_calculator.py             formula de recompensa post-trade
  tv_signal_parser.py              parser y validador del envelope TradingView
manager/
  qlearning_trainer.py             replay buffer, offline training, backups
strategies/
  strategy_tv_qlearning.py         logica de decision por accion Q-Learning
  pinescript/
    ema_atr_regime_v1.pine         estrategia PineScript para TradingView
dashboard/
  generate_dashboard.py            HTML con heatmap Q-Table y metricas
data/
  qlearning/
    q_table.json                   Q-Table persistida
    qlearning_stats.json           alpha, epsilon actuales
    replay_buffer.jsonl            historial de experiencias (s,a,r,s')
    backups/                       snapshots cada 6h (max 28)
utils/
  logger.py                        logger centralizado
scripts/
  send_tv_signal.ps1               plan B: enviar senal TV manualmente
  restore_qtable.ps1               restaurar Q-Table desde backup
  start_trading_stack.bat          arrancar el stack
docs/
  qlearning_strategy.md            descripcion completa del agente
  api_reference.md                 todos los endpoints documentados
  webhook_format.md                formato del envelope TradingView
  data_schemas.md                  schemas de q_table, replay_buffer, stats
  environment_variables.md         todas las variables de entorno
  end_to_end_flow.md               flujo completo de senal a trade a aprendizaje
tests/
  test_qlearning_agent.py          tests unitarios del agente Q-Learning
  fixtures/
    tv_envelope_buy.json           envelope de ejemplo para tests
```

## Variables de entorno importantes

| Variable             | Descripcion                       | Default |
|----------------------|-----------------------------------|---------|
| TV_WEBHOOK_SECRET    | Secreto para alertas TradingView  | -       |
| QLEARNING_ENABLED    | Activar agente Q-Learning         | true    |
| DRY_RUN              | No ejecutar ordenes reales        | true    |
| PORT                 | Puerto del servidor               | 8001    |

Ver `docs/environment_variables.md` para la lista completa.

## Documentacion

- [Estrategia Q-Learning](docs/qlearning_strategy.md)
- [API Reference](docs/api_reference.md)
- [Formato Webhook](docs/webhook_format.md)
- [Schemas de datos](docs/data_schemas.md)
- [Variables de entorno](docs/environment_variables.md)
- [Flujo end-to-end](docs/end_to_end_flow.md)
