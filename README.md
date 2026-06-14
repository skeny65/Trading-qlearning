# bot_ejecutor v2

## Estado: OPERATIVO — DRY_RUN (2026-05-28)

Router de ejecucion puro. Recibe señales de TradingView, BOT_GRID y BOT_MANAGER y ejecuta
ordenes directamente en **Binance Futures USDT-M**. Sin decision propia — si llega open, abre; si llega close, cierra.

```
TradingView  → POST /webhook/1-4
BOT_GRID     → JSONL polling (audit.jsonl cada 2s) + fallback /webhook/9
BOT_MANAGER  → POST /signal  (protocolo v2.0)
                    │
                    ▼
          bot_ejecutor (:8001)
                    │
                    ▼
          Binance Futures USDT-M
```

---

## Arranque rapido

```bash
# Opcion A — Launcher (abre los 3 bots + ngrok + monitor)
start_all.bat          # en la raiz de BOT_EJECUTOR

# Opcion B — Solo ejecutor
cd sistema
pip install -r requirements.txt
cp .env.example .env   # editar keys
python bot3.py
```

---

## Carpetas (1-10)

| ID | Emisor       | Estado   | Cierre           | Simbolos    | Binance | Balance |
|----|-------------|----------|------------------|-------------|---------|---------|
| 1  | tradingview | ENABLED  | dos_senales (TV) | CUALQUIERA  | OFF     | 100 USDT |
| 2  | tradingview | disabled | dos_senales (TV) | CUALQUIERA  | OFF     | 100 USDT |
| 3  | tradingview | disabled | dos_senales (TV) | CUALQUIERA  | OFF     | 100 USDT |
| 4  | tradingview | ENABLED  | dos_senales (TV) | CUALQUIERA  | OFF     | 100 USDT |
| 5  | generico    | disabled | una_senal_poller | CUALQUIERA  | OFF     | 100 USDT |
| 6  | generico    | disabled | una_senal_poller | CUALQUIERA  | OFF     | 100 USDT |
| 7  | generico    | disabled | una_senal_poller | CUALQUIERA  | OFF     | 100 USDT |
| 8  | generico    | disabled | una_senal_poller | CUALQUIERA  | OFF     | 100 USDT |
| 9  | bot_grid    | ENABLED  | bot_grid         | CUALQUIERA  | OFF     | 200 USDT |
| 10 | bot_manager | ENABLED  | bot_manager      | CUALQUIERA  | OFF     | 100 USDT |

**Simbolos**: Cada carpeta acepta cualquier par — el emisor decide el simbolo.
**Binance OFF/ON**: controlado por `binance_live` en cada `config.json` (hot-reload, sin reinicio).

---

## Config por carpeta

Cada carpeta tiene su `estrategias/estrategia_{id}/config.json`:

```json
{
  "id": "1",
  "emisor": "tradingview",
  "enabled": true,
  "modo_cierre": "dos_senales",
  "coloca_sltp_en_binance": false,
  "account_type": "futures_usdt",
  "sizing": {
    "tipo": "margen_fijo_usdt",
    "margen_usdt": 5.0,
    "leverage": 10
  },
  "symbols_permitidos": [],
  "balance_inicial_usdt": 100.0,
  "binance_live": false,
  "notas": ""
}
```

| Campo | Descripcion |
|-------|-------------|
| `enabled` | Recibe y procesa señales |
| `binance_live` | `true` = ejecuta en Binance real / `false` = simula (hot-reload) |
| `balance_inicial_usdt` | Capital inicial para tracking de balance |
| `symbols_permitidos` | Lista de simbolos permitidos. `[]` = acepta cualquier simbolo |
| `sizing.margen_usdt` | USDT de margen por operacion |
| `sizing.leverage` | Apalancamiento |

---

## Endpoints

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/` | Health check rapido |
| GET | `/health` | Estado completo + bot_grid + bot_manager |
| POST | `/webhook/{1-10}` | Señal TradingView / BOT_GRID (fallback) |
| POST | `/signal` | Señal BOT_MANAGER / BOT_GRID (protocolo v2.0) |
| GET | `/api/folders` | Config y posiciones de todas las carpetas |
| GET | `/api/folder/{id}/status` | Config + posiciones de una carpeta |
| GET | `/api/folder/{id}/metrics` | Winrate, PnL, balance |
| GET | `/api/metrics` | Consolidado global |
| GET | `/pending` | Posiciones monitoreadas por PricePoller |

---

## Formato señal TradingView (carpetas 1-4)

```json
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "buy",
    "signal_type": "open",
    "params": { "price": 155.20, "sl": 150.00, "tp": 165.00 }
  }
}
```

Cierre: segunda alerta con `signal_type: "close"` desde TradingView.

---

## Estructura

```
Bot_Ejecutor/
  bot_ejecutor.bat              ← arranca uvicorn + ngrok + monitor
  estrategias/
    estrategia_{1-10}/
      config.json               ← emisor, sizing, binance_live, balance_inicial_usdt
      trade_log_YYYY_MM.xlsx    ← Excel mensual (nuevo archivo cada mes)
      actividades/
        balance.json            ← balance USDT acumulado (persiste entre reinicios)
        senales_recibidas.jsonl ← toda señal recibida (incluye disabled)
        ejecuciones.jsonl       ← toda ejecucion open/close
        eventos/{ts}.json       ← un JSON por evento

  sistema/
    bot3.py                     ← FastAPI app principal
    config.py                   ← variables de entorno
    core/
      binance_executor.py       ← MARKET open/close/grid en Binance Futures
      folder_config.py          ← carga config.json por carpeta
      adapters/                 ← parsers por emisor (tv, grid, manager, generico)
    manager/
      price_poller.py           ← monitorea TP/SL (60s) para carpetas poller
      bot_grid_poller.py        ← lee audit.jsonl de BOT_GRID (2s)
      metrics.py                ← calcula winrate / pnl
    utils/
      excel_logger.py           ← escribe trade_log_YYYY_MM.xlsx (mensual)
      balance_tracker.py        ← gestiona balance USDT por carpeta
      logger.py
    sender/
      telegram_notifier.py
    scripts/
      health_monitor.ps1        ← monitor visual en consola (refresca 15s)
```

---

## Excel mensual

Cada cierre de mes genera un nuevo archivo `trade_log_YYYY_MM.xlsx`.
El primer trade del mes hereda el balance final del mes anterior (fila amarilla inicial).

Columnas: `fecha`, `hora_utc`, `symbol`, `side`, `precio_entrada`, `precio_salida`,
`duracion_min`, `resultado`, `pnl_pct`, `profit_usdt`, `balance_antes`, `balance_despues`.

---

## Variables de entorno (.env)

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `DRY_RUN` | `true` | Freno global — sobreescribe binance_live de todas las carpetas |
| `TV_WEBHOOK_SECRET` | — | Secret compartido con todos los emisores |
| `BINANCE_API_KEY` | — | API key Binance Futures USDT-M |
| `BINANCE_API_SECRET` | — | API secret Binance Futures USDT-M |
| `BINANCE_TESTNET` | `false` | Testnet de Binance |
| `BINANCE_DEFAULT_LEVERAGE` | `10` | Leverage por defecto si config.json no lo define |
| `BINANCE_DEFAULT_MARGIN_USDT` | `5.0` | Margen por defecto |
| `PORT` | `8001` | Puerto del servidor FastAPI |

---

## Ir a LIVE (por estrategia)

1. En `estrategias/estrategia_{id}/config.json`: `"binance_live": true`
2. En `sistema/.env`: `DRY_RUN=false`, `BINANCE_TESTNET=false`
3. Verificar API keys de Binance Futures con permiso de trading
4. Reiniciar bot — confirmar con `GET /health`

El cambio de `binance_live` en `config.json` es **hot-reload** (sin reinicio).
El cambio de `DRY_RUN` en `.env` requiere reinicio del bot.

---

## Health Monitor

```powershell
.\sistema\scripts\health_monitor.ps1
```

Muestra cada 15s: estado del ejecutor, carpeta 1 + ngrok, Bot_Grid, Bot_Manager,
resultados globales (trades, wins, losses, PnL, balance total).

---

## Tests

```bash
cd sistema
pytest tests/test_ejecutor.py -v
```
