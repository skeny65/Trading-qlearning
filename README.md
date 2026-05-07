# Bot3 - Q-Learning Trading Bot

## Estado: OPERATIVO (2026-05-06)

Primera orden real ejecutada en Alpaca Live:
- Senal: SPY BUY desde TradingView
- `order_id: 759b9684-528d-47cc-b54a-98aa68003a5a`

Trading bot que recibe alertas de **TradingView** (PineScript) y usa un agente
**Q-Learning** para decidir autonomamente si ejecutar, reducir, ignorar o invertir
cada senal. Las ordenes se ejecutan via **bot1** (Trading-bot) en Alpaca.
El agente aprende de cada operacion y mejora con el tiempo.

## Arquitectura

```
TradingView (.pine)
    |
    |  POST /webhook/tv  (X-Webhook-Secret)
    v
bot3 (localhost:8001)  --  Q-Learning decision
    |
    |  POST /webhook/bot3  (BOT1_WEBHOOK_SECRET)
    |  Latencia < 1ms (misma maquina)
    v
bot1 (localhost:8000)  --  Ejecuta en Alpaca
    |
    v
Alpaca API (Live / Paper)
    |
Q-Table (persist)       <-- aprende via POST /qlearning/update
replay_buffer.jsonl
auto-pausa por degradacion
```

## Arranque rapido

```bat
REM Doble clic en la raiz del proyecto:
start_bot3.bat
```

El bat hace todo automaticamente:
1. Verifica Python
2. Instala/actualiza dependencias (`pip install -r requirements.txt`)
3. Verifica conectividad con bot1 en localhost:8000
4. Arranca uvicorn en puerto 8001
5. Si cae, reinicia solo en 5 segundos (loop 24/7)

## Configuracion inicial

```bat
REM Copiar ejemplo de configuracion
copy .env.example .env
REM Editar .env con tus valores
```

Variables minimas a configurar:

```env
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret   # mismo que BOT3_WEBHOOK_SECRET en bot1
TV_WEBHOOK_SECRET=mi_secreto_webhook_123   # poner tambien en TradingView
DRY_RUN=false
PORT=8001
```

## Verificar que funciona

```powershell
# Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# Estado Q-Learning
Invoke-WebRequest http://localhost:8001/qlearning/status | Select-Object -ExpandProperty Content

# Enviar senal de prueba
$headers = @{ "Content-Type" = "application/json"; "X-Webhook-Secret" = "mi_secreto_webhook_123" }
$body = Get-Content tests\fixtures\tv_envelope_buy.json -Raw -Encoding UTF8
Invoke-WebRequest -Uri http://localhost:8001/webhook/tv -Method POST -Headers $headers -Body $body
```

## Endpoints principales

| Metodo | Endpoint              | Descripcion                                  |
|--------|-----------------------|----------------------------------------------|
| GET    | /                     | Health check rapido                          |
| GET    | /health               | Estado detallado (mode, agent, pending)      |
| POST   | /webhook/tv           | Recibir alertas de TradingView               |
| GET    | /qlearning/status     | Alpha, epsilon, best/worst state-action      |
| GET    | /qlearning/qtable     | Q-table completa en JSON                     |
| POST   | /qlearning/update     | Aprendizaje cuando cierra una posicion       |
| POST   | /qlearning/pause      | Pausar agente manualmente                    |
| POST   | /qlearning/resume     | Reanudar agente manualmente                  |
| GET    | /pending              | Decisiones pendientes de cierre              |

## Ciclo de aprendizaje

Cuando una posicion se cierra (TP, SL, o manual), enviar el resultado:

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

## Tests

```powershell
python -X utf8 -m pytest tests/ -v
# 6/6 pasan
```

## Integracion con bot1

Para que bot1 acepte senales de bot3, agregar en el `.env` de bot1:

```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

Y registrar `"bot3_qlearning"` en `KNOWN_BOTS` de `core/bot_registry.py`.

Ver `docs/integration_bot1.md` para los detalles completos.

## Estructura del proyecto

```
bot3.py                             FastAPI entrypoint + todos los endpoints
config.py                           Variables de entorno y configuracion
start_bot3.bat                      Launcher 24/7 con auto-restart
requirements.txt
.env                                Configuracion local (gitignored)
.env.example                        Plantilla de configuracion

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

sender/
  webhook_client.py                POST a bot1 con retry backoff
  signal_formatter.py              construye el payload para bot1
  telegram_notifier.py             notificaciones Telegram

utils/
  logger.py                        logger centralizado
  excel_logger.py                  exportacion a Excel

dashboard/
  generate_dashboard.py            HTML con heatmap Q-Table y metricas

data/
  qlearning/
    q_table.json                   Q-Table persistida
    qlearning_stats.json           alpha, epsilon actuales
    replay_buffer.jsonl            historial de experiencias (s,a,r,s')
    backups/                       snapshots cada 6h (max 28)

state/
  decision_log.jsonl               historial de todas las decisiones
  pending_signals.json             senales en cola para retry

logs/
  YYYY-MM-DD_HH-MM-SS.json        reporte por evento
  trade_log.xlsx                   Excel acumulado

scripts/
  setup/
    setup_project.py               generador del proyecto (ya ejecutado)
  send_tv_signal.ps1               enviar senal TV manualmente
  restore_qtable.ps1               restaurar Q-Table desde backup

tests/
  test_qlearning_agent.py          tests unitarios (6/6 pasan)
  fixtures/
    tv_envelope_buy.json           envelope de ejemplo para tests

docs/
  architecture.md                  diagrama de componentes
  qlearning_strategy.md            descripcion completa del agente
  api_reference.md                 todos los endpoints documentados
  webhook_format.md                formato del envelope TradingView
  data_schemas.md                  schemas de q_table, replay_buffer, stats
  environment_variables.md         todas las variables de entorno
  end_to_end_flow.md               flujo completo de senal a trade a aprendizaje
  integration_bot1.md              integracion con bot1 (cambios aplicados)
  SETUP_INSTRUCTIONS.md            instrucciones de setup y arranque
```

## Variables de entorno importantes

| Variable              | Descripcion                            | Default |
|-----------------------|----------------------------------------|---------|
| BOT1_WEBHOOK_URL      | URL del endpoint bot3 en bot1          | -       |
| BOT1_WEBHOOK_SECRET   | Secreto compartido con bot1            | -       |
| TV_WEBHOOK_SECRET     | Secreto para alertas TradingView       | -       |
| QLEARNING_ENABLED     | Activar agente Q-Learning              | true    |
| DRY_RUN               | No enviar ordenes reales a bot1        | false   |
| PORT                  | Puerto del servidor                    | 8001    |

Ver `docs/environment_variables.md` para la lista completa.

## Documentacion

- [Instrucciones de setup](docs/SETUP_INSTRUCTIONS.md)
- [Arquitectura](docs/architecture.md)
- [Integracion con bot1](docs/integration_bot1.md)
- [Flujo end-to-end](docs/end_to_end_flow.md)
- [Estrategia Q-Learning](docs/qlearning_strategy.md)
- [API Reference](docs/api_reference.md)
- [Formato Webhook](docs/webhook_format.md)
- [Schemas de datos](docs/data_schemas.md)
- [Variables de entorno](docs/environment_variables.md)
