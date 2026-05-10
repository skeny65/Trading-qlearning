# Bot3 - Q-Learning Trading Bot (Multi-Strategy)

## Estado: OPERATIVO (2026-05-09)

Trading bot que recibe alertas de **TradingView** y usa agentes **Q-Learning independientes**
por estrategia para decidir autonomamente si ejecutar, reducir, ignorar o invertir cada senal.

El sistema aprende solo: el **Price Poller** (Binance API) detecta cuando cada posicion toca
TP o SL, actualiza la Q-table automaticamente, y llena el Excel con WIN/LOSS sin intervencion humana.

## Arquitectura

```
TradingView (.pine)
    |
    |  POST /webhook/strategy/{id}
    v
bot3 (localhost:8001)
    |
    +-- StrategyRegistry
    |     |-- ApuestaWorker   (state 3D: 27 estados)
    |     |-- QLearningWorker (state 5D: 243 estados)
    |     +-- TanqueWorker    (state 3D: 27 estados)
    |
    |-- Excel por estrategia: logs/{id}/trade_log.xlsx
    |
    |  POST /webhook/bot3  (opcional, si bot1 esta corriendo)
    v
bot1 (localhost:8000)  -- Ejecuta en Alpaca

PricePoller (hilo independiente, cada 60s)
    |-- GET https://api.binance.com/api/v3/ticker/price
    |-- Detecta TP/SL
    |-- Actualiza Q-table automaticamente
    +-- Llena Excel: result=WIN/LOSS, pnl_notes, learned_at
```

## Estrategias

| ID         | Estado  | State space        | Descripcion                          |
|------------|---------|--------------------|--------------------------------------|
| qlearning  | Activa  | 5D - 243 estados   | regime, momentum, setup, htf, trend  |
| apuesta    | Activa  | 3D - 27 estados    | price_zone, rr_level, hour_zone      |
| tanque     | Activa  | 3D - 27 estados    | entry_strength, bar_zone, pattern    |

## Arranque rapido

```bat
start_bot3.bat
```

Hace todo: verifica Python, instala deps, abre ngrok, arranca uvicorn con auto-restart 24/7.

## Excel automatico

Cada estrategia tiene su propio Excel en `logs/{id}/trade_log.xlsx`.
El bot escribe una fila por cada alerta. El Price Poller llena automaticamente:

| Columna    | Quien la llena | Contenido ejemplo                           |
|------------|----------------|---------------------------------------------|
| result     | Price Poller   | `WIN` o `LOSS`                              |
| pnl_notes  | Price Poller   | `+1.45% \| TP_HIT \| 47min \| R=2.34x`     |
| learned_at | Price Poller   | `2026-05-09T15:10:00Z`                      |

Para forzar aprendizaje desde Excel (si quieres corregir algun resultado):
```powershell
python scripts/learn_from_excel.py
```

## Endpoints principales

| Metodo | Endpoint                          | Descripcion                              |
|--------|-----------------------------------|------------------------------------------|
| GET    | /health                           | Estado completo (strategies, poller)     |
| POST   | /webhook/strategy/{id}            | Recibir alertas de TradingView           |
| GET    | /api/strategies                   | Listar todas las estrategias             |
| GET    | /api/strategy/{id}/status         | Estado del agente                        |
| POST   | /api/strategy/{id}/pause          | Pausar agente                            |
| POST   | /api/strategy/{id}/resume         | Reanudar agente                          |
| POST   | /api/strategy/{id}/update         | Aprendizaje manual                       |
| GET    | /api/strategy/{id}/journal        | Resumen del diario de aprendizaje        |
| GET    | /api/strategy/{id}/journal/report | Ver INSIGHTS.md                          |
| GET    | /pending                          | Posiciones monitoreadas por Price Poller |

## Verificar que funciona

```powershell
# Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# Estado de todas las estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# Diario de aprendizaje
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal | Select-Object -ExpandProperty Content

# Ver Excel actualizado
# Abrir: logs\qlearning\trade_log.xlsx

# Ver INSIGHTS.md
Get-Content logs\qlearning\INSIGHTS.md
```

## Configuracion minima (.env)

```env
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret
TV_WEBHOOK_SECRET=mi_secreto_webhook_123
DRY_RUN=false
PORT=8001
```

## Estructura del proyecto

```
bot3.py                               FastAPI entrypoint
config.py                             Variables de entorno
start_bot3.bat                        Launcher 24/7 con auto-restart
requirements.txt
.env / .env.example

core/
  qlearning_agent.py                 Q-Table, epsilon-greedy, Bellman
  strategy_worker.py                 Clase base abstracta
  strategy_registry.py               Singleton con todos los workers
  reward_calculator.py               Formula de recompensa
  tv_signal_parser.py                Parser del envelope TradingView

strategies/
  apuesta/worker.py                  Estrategia Apuesta (3D)
  qlearning/worker.py                Estrategia QLearning (5D)
  tanque/worker.py                   Estrategia Tanque (3D)

manager/
  qlearning_trainer.py               Replay buffer, backups
  price_poller.py                    Monitor Binance cada 60s -> Excel automatico
  learning_journal.py                Diario de aprendizaje -> INSIGHTS.md

utils/
  excel_logger.py                    Excel por estrategia (write + update result)

sender/
  webhook_client.py                  POST a bot1 con retry
  signal_formatter.py                Payload para bot1
  telegram_notifier.py               Notificaciones Telegram

scripts/
  learn_from_excel.py                Leer WIN/LOSS del Excel -> aprendizaje manual

data/strategies/{id}/                Q-table, stats, replay, backups (por estrategia)
state/{id}/decision_log.jsonl        Historial de decisiones (por estrategia)
logs/{id}/
  trade_log.xlsx                     Excel con resultados automaticos
  INSIGHTS.md                        Resumen de aprendizaje
  learning_journal.jsonl             Registro detallado por Q-update
  events/                            Reporte JSON por evento

docs/                                Documentacion completa
tests/                               Tests unitarios
```

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
