# Bot3 - Q-Learning Trading Bot (Multi-Strategy)

## Estado: OPERATIVO (2026-05-06)

Primera orden real ejecutada en Alpaca Live:
- Senal: SPY BUY desde TradingView
- `order_id: 759b9684-528d-47cc-b54a-98aa68003a5a`

Trading bot que recibe alertas de **TradingView** (PineScript) y usa agentes
**Q-Learning independientes** por estrategia para decidir autonomamente si ejecutar,
reducir, ignorar o invertir cada senal. Las ordenes se ejecutan via **bot1** (Trading-bot).

Cada estrategia es completamente independiente: Q-table propia, logs propios, diario de
aprendizaje propio. El sistema aprende solo gracias al **Price Poller** (Binance API).

## Arquitectura

```
TradingView (.pine)
    |
    |  POST /webhook/strategy/{id}  (X-Webhook-Secret)
    v
bot3 (localhost:8001)
    |
    +-- StrategyRegistry
    |     |-- ApuestaWorker   -> data/strategies/apuesta/
    |     |-- QLearningWorker -> data/strategies/qlearning/
    |     +-- TanqueWorker    -> data/strategies/tanque/
    |
    |  (decision Q-Learning por estrategia)
    |
    |  POST /webhook/bot3  (BOT1_WEBHOOK_SECRET)
    v
bot1 (localhost:8000)  -- Ejecuta en Alpaca
    |
    v
Alpaca API (Live / Paper)

PricePoller (hilo independiente, Binance API publica)
    |-- GET https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT
    |-- Detecta TP/SL cada 30s
    +-- Llama worker.update_q() automaticamente -> cierra el ciclo de aprendizaje
```

## Estrategias disponibles

| ID         | Estado  | Descripcion                                         |
|------------|---------|-----------------------------------------------------|
| qlearning  | Activa  | Estado 5D: 243 combinaciones de mercado             |
| apuesta    | Activa  | Estado 3D: zone de precio, R:R, hora del dia        |
| tanque     | Activa  | Estado 3D: fuerza de entrada, zona de vela, patron  |

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
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret
TV_WEBHOOK_SECRET=mi_secreto_webhook_123
DRY_RUN=false
PORT=8001
```

## Verificar que funciona

```powershell
# Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# Listar todas las estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# Estado de una estrategia
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/status | Select-Object -ExpandProperty Content

# Enviar senal de prueba a la estrategia qlearning
$headers = @{ "Content-Type" = "application/json"; "X-Webhook-Secret" = "mi_secreto_webhook_123" }
$body = Get-Content tests\fixtures\tv_envelope_buy.json -Raw -Encoding UTF8
Invoke-WebRequest -Uri http://localhost:8001/webhook/strategy/qlearning -Method POST -Headers $headers -Body $body
```

## Endpoints principales

| Metodo | Endpoint                                | Descripcion                                    |
|--------|-----------------------------------------|------------------------------------------------|
| GET    | /                                       | Health check rapido                            |
| GET    | /health                                 | Estado detallado (strategies, poller, pending) |
| POST   | /webhook/strategy/{id}                  | Recibir alertas de TradingView por estrategia  |
| GET    | /api/strategies                         | Listar todas las estrategias                   |
| GET    | /api/strategy/{id}/status               | Estado del agente de una estrategia            |
| POST   | /api/strategy/{id}/pause                | Pausar estrategia manualmente                  |
| POST   | /api/strategy/{id}/resume               | Reanudar estrategia manualmente                |
| POST   | /api/strategy/{id}/update               | Aprendizaje manual (si no usa Price Poller)    |
| GET    | /api/strategy/{id}/journal              | Resumen del diario de aprendizaje              |
| GET    | /api/strategy/{id}/journal/recent       | Ultimas entradas del journal                   |
| GET    | /api/strategy/{id}/journal/report       | Regenerar INSIGHTS.md                         |
| GET    | /pending                                | Decisiones pendientes de cierre                |

## Ciclo de aprendizaje automatico (Price Poller)

El bot aprende solo. Cuando TradingView manda una alerta con `sl` y `tp`:

1. Bot3 ejecuta la orden y guarda en `pending_q_decisions` con `entry_price`, `sl`, `tp`
2. El Price Poller (hilo en segundo plano) consulta Binance cada 30 segundos
3. Cuando el precio toca `tp` o `sl`, llama automaticamente a `worker.update_q()`
4. El agente actualiza la Q-table y regenera `INSIGHTS.md`

No se necesita intervenci n manual. El ciclo cierra solo.

## Diario de aprendizaje (INSIGHTS.md)

Cada estrategia genera su propio archivo en `logs/{strategy_id}/INSIGHTS.md`:

- Estados RENTABLES (Q > 0.30): donde el agente prefiere ejecutar
- Estados BLOQUEADOS (Q < -0.30): donde el agente evita entrar automaticamente
- Ultimas 15 conclusiones con etiquetas `[RENTABLE]` / `[BLOQUEADO]`
- Sugerencias de mejora para Pine Script

El archivo se sobreescribe despues de cada trade. Siempre esta al dia.

## Tests

```powershell
python -X utf8 -m pytest tests/ -v
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
bot3.py                               FastAPI entrypoint + todos los endpoints
config.py                             Variables de entorno y configuracion
start_bot3.bat                        Launcher 24/7 con auto-restart
requirements.txt
.env                                  Configuracion local (gitignored)
.env.example                          Plantilla de configuracion

core/
  qlearning_agent.py                 Q-Table, epsilon-greedy, Bellman update
  strategy_worker.py                 Clase base abstracta para todas las estrategias
  strategy_registry.py               Singleton: carga e inicializa todos los workers
  state_encoder.py                   (legacy) encoder para el endpoint /webhook/tv
  reward_calculator.py               formula de recompensa post-trade
  tv_signal_parser.py                parser y validador del envelope TradingView

strategies/
  apuesta/
    worker.py                        Estrategia Apuesta: state price_zone|rr_level|hour_zone
  qlearning/
    worker.py                        Estrategia QLearning: state 5D (243 estados)
  tanque/
    worker.py                        Estrategia Tanque: state entry_strength|bar_zone|pattern
  pinescript/
    ema_atr_regime_v1.pine           estrategia PineScript para TradingView

manager/
  qlearning_trainer.py               replay buffer, offline training, backups
  price_poller.py                    hilo independiente: Binance -> deteccion TP/SL
  learning_journal.py                diario de aprendizaje por estrategia

sender/
  webhook_client.py                  POST a bot1 con retry backoff
  signal_formatter.py                construye el payload para bot1
  telegram_notifier.py               notificaciones Telegram

utils/
  logger.py                          logger centralizado
  excel_logger.py                    exportacion a Excel (por estrategia)

data/
  strategies/
    apuesta/
      q_table.json                   Q-Table de la estrategia apuesta
      qlearning_stats.json           alpha, epsilon actuales
      replay_buffer.jsonl            historial de experiencias
      backups/                       snapshots automaticos
    qlearning/
      q_table.json
      qlearning_stats.json
      replay_buffer.jsonl
      backups/
    tanque/
      q_table.json
      qlearning_stats.json
      replay_buffer.jsonl
      backups/

state/
  apuesta/
    decision_log.jsonl               historial de decisiones de la estrategia apuesta
  qlearning/
    decision_log.jsonl
  tanque/
    decision_log.jsonl
  pending_signals.json               senales en cola para retry

logs/
  apuesta/
    INSIGHTS.md                      diario de aprendizaje (actualizado tras cada trade)
    learning_journal.jsonl           registro maquina de Q-updates
    trade_log.xlsx                   Excel acumulado
    events/                          reportes JSON por evento
  qlearning/
    INSIGHTS.md
    learning_journal.jsonl
    trade_log.xlsx
    events/
  tanque/
    INSIGHTS.md
    learning_journal.jsonl
    trade_log.xlsx
    events/

tests/
  test_qlearning_agent.py
  fixtures/
    tv_envelope_buy.json

docs/
  architecture.md
  qlearning_strategy.md
  api_reference.md
  webhook_format.md
  data_schemas.md
  environment_variables.md
  end_to_end_flow.md
  integration_bot1.md
  SETUP_INSTRUCTIONS.md
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
- [Flujo end-to-end](docs/end_to_end_flow.md)
- [Estrategia Q-Learning](docs/qlearning_strategy.md)
- [API Reference](docs/api_reference.md)
- [Formato Webhook](docs/webhook_format.md)
- [Schemas de datos](docs/data_schemas.md)
- [Variables de entorno](docs/environment_variables.md)
- [Integracion con bot1](docs/integration_bot1.md)
