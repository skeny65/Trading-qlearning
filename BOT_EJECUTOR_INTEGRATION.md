# BOT_EJECUTOR — Protocolo de Integración Completo

**Versión del contrato:** `2.0`
**Archivo:** `Bot_Ejecutor/BOT_EJECUTOR_INTEGRATION.md`
**Documentos relacionados:**
- `Bot_Grid/BOT_EJECUTOR_INTEGRATION.md` — perspectiva BOT_GRID
- `Bot_Manager/BOT_EXECUTOR_INTEGRATION.md` — perspectiva BOT_MANAGER

---

## 1. Principio fundamental

BOT_EJECUTOR es el **único componente que toca Binance**. No toma decisiones propias.
Si llega `open` → abre la posición. Si llega `close` → cierra la posición.
Los tres emisores (TradingView, BOT_GRID, BOT_MANAGER) generan las señales; el ejecutor solo ejecuta.

---

## 2. Arquitectura general

```
┌────────────────────┐  POST /webhook/1-4
│   TRADING_VIEW     │ ─────────────────────────────────────────────────────┐
│   (alertas Pine)   │                                                       │
└────────────────────┘                                                       │
                                                                             ▼
┌────────────────────┐  JSONL polling (audit.jsonl cada 2s)       ┌─────────────────────┐       ┌─────────────┐
│     BOT_GRID       │ ──────────────────────────────────────────▶ │   BOT_EJECUTOR      │ ─────▶│   BINANCE   │
│  (grid trading)    │  ─ también: POST /webhook/9 (fallback) ──▶  │   localhost:8001    │       │ Futures     │
└────────────────────┘                                             │                     │       │ USDT-M      │
                                                                   └─────────────────────┘       └─────────────┘
┌────────────────────┐  POST /signal (HTTP, protocolo v2.0)                 ▲
│    BOT_MANAGER     │ ───────────────────────────────────────────────────── ┘
│ (trend/momentum)   │
└────────────────────┘
```

---

## 3. Carpetas asignadas por emisor

| Carpeta | Emisor       | Símbols          | Modo cierre       | Estado   | Activa por  |
|---------|-------------|-----------------|------------------|---------|-------------|
| 1       | tradingview | SOLUSDT          | dos_senales       | ENABLED  | 2ª alerta TV |
| 2       | tradingview | SOLUSDT          | dos_senales       | disabled | 2ª alerta TV |
| 3       | tradingview | SOLUSDT          | dos_senales       | disabled | 2ª alerta TV |
| 4       | tradingview | ETHUSDT          | dos_senales       | ENABLED  | 2ª alerta TV |
| 5–8     | generico    | (libre)          | una_senal_poller  | disabled | PricePoller  |
| 9       | bot_grid    | ETHUSDT          | bot_grid          | ENABLED  | BotGridPoller |
| 10      | bot_manager | ETHUSDT, BTCUSDT | bot_manager       | ENABLED  | señal CLOSE  |

Configs en: `estrategias/estrategia_{id}/config.json` — se releen en cada señal sin reiniciar.

---

## 4. Sizing (por carpeta)

Cada carpeta tiene capital completamente independiente. El sizing se define en `config.json`:

```json
"sizing": {
  "tipo": "margen_fijo_usdt",
  "margen_usdt": 5.0,
  "leverage": 10
}
```

```
notional = margen_usdt × leverage   →  5.0 × 10 = 50 USDT
qty_raw  = notional / price
qty      = redondear_hacia_abajo(qty_raw, step_size_Binance)

Ejemplo ETHUSDT a $3000:
  notional = 50 USDT
  qty_raw  = 50 / 3000 = 0.01666...
  step     = 0.001 → qty = 0.016 ETH
```

Una carpeta nunca consume el balance de otra.

---

## 5. Integración: TRADING_VIEW → carpetas 1–4

### Canal de transporte

```
TradingView alerta Pine Script
    │
    │  POST http://localhost:8001/webhook/{1-4}
    │  — o —
    │  POST https://shaft-goliath-shakable.ngrok-free.dev/webhook/{1-4}
    │
    ▼
bot_ejecutor (adapter_tradingview.py → SignalInterna)
    │
    ▼
_execute_open() o _execute_close()  [BackgroundTask]
    │
    ▼
Binance Futures USDT-M  (MARKET order)
```

### Headers requeridos

```http
POST /webhook/1
Content-Type: application/json
x-webhook-secret: mi_secreto_webhook_123
```

O como query param: `/webhook/1?secret=mi_secreto_webhook_123`

### Señal OPEN

```json
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "buy",
    "signal_type": "open",
    "size": 0.1,
    "params": {
      "price": 155.20,
      "sl": 150.00,
      "tp": 165.00
    }
  }
}
```

### Señal CLOSE (segunda alerta)

```json
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "close_buy",
    "signal_type": "close",
    "size": 0.1,
    "params": {
      "price": 165.00,
      "entry_price": 155.20,
      "pnl_pct": 6.31,
      "close_reason": "Cruce EMA contrario"
    }
  }
}
```

### Campos clave

| Campo | Open | Close | Descripción |
|-------|------|-------|-------------|
| `status` | `"pending"` | `"pending"` | Cualquier otro valor → señal ignorada |
| `signal.symbol` | REQUERIDO | REQUERIDO | Ej. `"SOLUSDT"` |
| `signal.action` | `"buy"` `"sell"` | `"close_buy"` `"close_sell"` | Determina el lado |
| `signal.signal_type` | `"open"` | `"close"` | Tipo de operación |
| `params.price` | REQUERIDO | REQUERIDO | Precio de mercado actual |
| `params.sl` | opcional | — | Stop loss |
| `params.tp` | opcional | — | Take profit |
| `params.pnl_pct` | — | opcional | Si no viene, se calcula |
| `params.close_reason` | — | opcional | Texto libre |

### Modo de cierre `dos_senales`

TradingView gestiona todo: envía `signal_type=open` para abrir y `signal_type=close` para cerrar.
El `PricePoller` **NO** monitorea estas carpetas.
`coloca_sltp_en_binance: false` → Binance no tiene órdenes SL/TP; TradingView controla el cierre.

---

## 6. Integración: BOT_GRID → carpeta 9

### Canal primario: JSONL file polling

BOT_GRID escribe sus señales en un archivo JSONL compartido. BOT_EJECUTOR lo lee cada 2 segundos.

```
BOT_GRID genera señal
    │
    │  append a: C:/Users/kenyb/Desktop/GEMINI/BOT-GRID/logs/signals/audit.jsonl
    │  (una línea JSON por señal)
    │
    ▼
BotGridPoller (hilo daemon, cada 2s)
    │  lee nuevas líneas desde el último offset
    │  valida: version=="2.0", TTL < 60s, symbol permitido
    │
    ▼
_handle_open / _handle_close / _handle_adjust
    │
    ▼
binance_executor.open_grid / close_grid_position / adjust_grid
    │
    ▼
Binance Futures:  LIMIT orders (grid) / MARKET reduceOnly (cierre)
```

### Canal secundario: HTTP POST (fallback)

```http
POST http://localhost:8001/webhook/9
Content-Type: application/json
x-webhook-secret: mi_secreto_webhook_123
```

Soporta el mismo formato v2.0. ADJUST_GRID via HTTP es ignorado (solo funciona por JSONL).

### Config carpeta 9

```json
{
  "id": "9",
  "emisor": "bot_grid",
  "enabled": true,
  "modo_cierre": "bot_grid",
  "coloca_sltp_en_binance": false,
  "sizing": { "tipo": "margen_fijo_usdt", "margen_usdt": 5.0, "leverage": 10 },
  "symbols_permitidos": ["ETHUSDT"],
  "bot_grid_config": {
    "audit_log_path": "C:/Users/kenyb/Desktop/GEMINI/BOT-GRID/logs/signals/audit.jsonl",
    "polling_interval_seconds": 2,
    "expected_version": "2.0",
    "max_signal_age_seconds": 60
  }
}
```

### Protocolo v2.0 — estructura del payload

```json
{
  "version": "2.0",
  "signal_id": "a3f1c2d4-8e7b-4f01-bc23-9d5e6a7f8012",
  "timestamp_utc": "2026-05-28T14:32:00Z",
  "symbol": "ETHUSDT",
  "action": "OPEN_GRID",
  "mode": "RANGING",
  "params": { ... },
  "context": { ... },
  "expires_in_seconds": 60
}
```

| Acción | Efecto en BOT_EJECUTOR | Binance |
|--------|----------------------|---------|
| `OPEN_GRID` | Abre N órdenes LIMIT entre `range_lower` y `range_upper` | N × LIMIT GTC + SL STOP_MARKET |
| `ADJUST_GRID` | Cancela todas las órdenes pendientes y recoloca con nuevos params | cancel_all → N × LIMIT nuevas |
| `CLOSE_GRID` | Cancela todas las órdenes y cierra la posición neta | cancel_all + MARKET reduceOnly |

Detalle del payload y ejemplos en: `Bot_Grid/BOT_EJECUTOR_INTEGRATION.md`

---

## 7. Integración: BOT_MANAGER → carpeta 10

### Canal: HTTP POST /signal

```http
POST http://localhost:8001/signal
Content-Type: application/json
X-Secret: mi_secreto_webhook_123
```

El endpoint `/signal` es el canal unificado para BOT_MANAGER y también acepta BOT_GRID via HTTP.

### Protocolo v2.0 — estructura del payload

```json
{
  "signal_id":   "f3a2c1d4-8b9e-4f2a-a1b3-0c5d7e8f9a0b",
  "source":      "bot_manager",
  "timestamp":   "2026-05-28T14:32:00Z",
  "action":      "OPEN",
  "symbol":      "ETHUSDT",
  "side":        "BUY",
  "price":       3248.50,
  "sl":          3201.20,
  "tp":          3342.00,
  "position_id": "MGR-ETH-001"
}
```

| Acción | Requerido | Efecto en BOT_EJECUTOR | Binance |
|--------|-----------|----------------------|---------|
| `OPEN` | `side`, `sl` | Abre posición | MARKET order |
| `CLOSE` | `position_id` | Cierra posición | cancel_all + MARKET reduceOnly |
| `ADJUST` | `position_id` | Mueve SL/TP | cancel_all + nueva STOP_MARKET / TAKE_PROFIT_MARKET |
| `PAUSE` | — | Bloquea nuevas entradas del source | (ninguna) |
| `RESUME` | — | Reactiva entradas del source | (ninguna) |

Detalle del payload y ejemplos en: `Bot_Manager/BOT_EXECUTOR_INTEGRATION.md`

---

## 8. Respuestas del bot_ejecutor

### Endpoint /webhook/{id} (TradingView y BOT_GRID fallback)

| Situación | HTTP | Body |
|-----------|------|------|
| Éxito (ejecutando en background) | 200 | `{"ok": true}` |
| Carpeta deshabilitada | 200 | `{"ok": true, "skipped": "disabled"}` |
| Symbol no permitido | 200 | `{"ok": true, "skipped": "symbol X no permitido"}` |
| Posición ya abierta (mismo symbol) | 200 | `{"ok": true, "skipped": "posicion ya abierta para X"}` |
| Señal ignorada (status != pending) | 200 | `{"ok": true, "skipped": "status=ok — sin accion"}` |
| JSON inválido | 400 | `{"detail": "JSON invalido"}` |
| Payload mal formado | 422 | `{"detail": "Payload invalido: <motivo>"}` |
| Secret incorrecto | 401 | `{"detail": "Webhook secret invalido"}` |
| Carpeta fuera de rango (>10) | 404 | `{"detail": "Carpeta '11' no existe (1-10)"}` |

La respuesta llega en < 100ms. La ejecución en Binance corre en BackgroundTask.

### Endpoint /signal (BOT_MANAGER y BOT_GRID via HTTP)

| Situación | HTTP | Body |
|-----------|------|------|
| Señal aceptada | 200 | `{"status": "accepted", "signal_id": "...", "queued_at": "...", "executor_mode": "dry-run"}` |
| Señal duplicada | 200 | `{"status": "duplicate", "signal_id": "..."}` |
| Carpeta deshabilitada | 200 | `{"status": "accepted", "signal_id": "...", "skipped": "folder_disabled"}` |
| Symbol no permitido | 200 | `{"status": "accepted", "signal_id": "...", "skipped": "symbol X no permitido"}` |
| Señal expirada (> 5 min) | 422 | `{"detail": "stale signal: 310s old"}` |
| Campo faltante | 422 | `{"detail": "missing_field: sl"}` |
| Secret incorrecto | 401 | `{"detail": "Webhook secret invalido"}` |

---

## 9. Endpoints de monitoreo

```
GET  http://localhost:8001/              → health check rápido
GET  http://localhost:8001/health        → estado detallado + pollers + posiciones
GET  http://localhost:8001/pending       → posiciones en PricePoller
GET  http://localhost:8001/api/folders   → config + posiciones de todas las carpetas
GET  http://localhost:8001/api/folder/9/status   → config + posiciones carpeta 9
GET  http://localhost:8001/api/folder/9/metrics  → winrate, PnL carpeta 9
GET  http://localhost:8001/api/metrics           → métricas consolidadas globales
```

Respuesta `/health`:

```json
{
  "status": "ok",
  "dry_run_global": true,
  "carpetas_activas": ["1", "4", "9", "10"],
  "carpetas_dry_run_local": [],
  "posiciones_abiertas": 0,
  "poller_monitored": 0,
  "price_poller": { "running": true, "poll_interval_sec": 60 },
  "bot_grid_poller": { "running": true, "poll_interval_sec": 2, "grid_folders": ["9"] },
  "bot_grid": {
    "status": "OK", "symbol": "ETHUSDT", "dry_run": true,
    "ws_silence_sec": 1.4, "executor_alive": true, "signals_sent": 0
  },
  "bot_manager": {
    "status": "ok", "mode": "alertas", "last_scan": "2026-05-28T22:00:10Z",
    "open_positions": 0, "circuit_open": false, "paused": false
  }
}
```

`dry_run_global=true` en `.env` sobreescribe a todas las carpetas.
`carpetas_dry_run_local` muestra carpetas con `binance_live: false` cuando el global es false.

---

## 10. Flujos end-to-end

### Flujo A: TradingView → Open → Close

```
1. TV dispara alerta OPEN
       POST /webhook/1  {"status":"pending","signal":{"signal_type":"open",...}}

2. bot3.py
   ├─ Valida secret
   ├─ Carga config.json carpeta 1
   ├─ adapter_tradingview.parse() → SignalInterna {tipo="open"}
   ├─ Log → senales_recibidas.jsonl
   ├─ Check: enabled? Check: symbol permitido? Check: posicion ya abierta?
   └─ BackgroundTask: _execute_open()
         ├─ DRY_RUN: simula order_id
         │  LIVE:    binance_executor.open_position(SOLUSDT, buy, price, sizing)
         │            → futures_change_leverage(10)
         │            → MARKET BUY qty=X
         │            → (sin SL/TP en Binance — coloca_sltp_en_binance=false)
         ├─ open_positions[("1","SOLUSDT")] = {order_id, side, entry_price, ...}
         ├─ Excel: fila PENDING
         └─ ejecuciones.jsonl + eventos/{ts}.json
   → {"ok": true}

3. TV dispara alerta CLOSE
       POST /webhook/1  {"status":"pending","signal":{"signal_type":"close",...}}

4. bot3.py
   └─ BackgroundTask: _execute_close()
         ├─ open_pos = open_positions.pop(("1","SOLUSDT"))
         ├─ pnl_pct calculado desde entry_price
         ├─ DRY_RUN: log / LIVE: binance_executor.close_position(SOLUSDT)
         │            → cancel_all_open_orders
         │            → get_position_qty → MARKET SELL reduceOnly
         ├─ update_excel_result(order_id, WIN/LOSS, pnl_pct)
         └─ ejecuciones.jsonl + eventos/{ts}.json
```

### Flujo B: BOT_GRID → OPEN_GRID → CLOSE_GRID

```
1. BOT_GRID escribe en audit.jsonl:
   {"version":"2.0","action":"OPEN_GRID","symbol":"ETHUSDT","params":{...},"expires_in_seconds":60}

2. BotGridPoller (cada 2s)
   ├─ Lee nuevas líneas desde offset
   ├─ Valida version=="2.0" y TTL < 60s
   └─ _handle_open()
         ├─ DRY_RUN: simula / LIVE: binance_executor.open_grid(ETHUSDT, buy, params, sizing)
         │            → futures_change_leverage(10)
         │            → N × LIMIT BUY entre range_lower y price_base
         │            → STOP_MARKET SL
         ├─ open_positions[("9","ETHUSDT")] = {order_id, grid=True, ...}
         └─ Excel: fila PENDING

3. BOT_GRID escribe en audit.jsonl:
   {"version":"2.0","action":"CLOSE_GRID","symbol":"ETHUSDT","close_reason":"tp_reached"}

4. BotGridPoller
   └─ _handle_close()
         ├─ open_positions.pop(("9","ETHUSDT"))
         ├─ LIVE: binance_executor.close_grid_position(ETHUSDT)
         │            → cancel_all_open_orders
         │            → MARKET SELL reduceOnly
         └─ update_excel_result(WIN/LOSS, pnl_pct)
```

### Flujo C: BOT_MANAGER → OPEN → ADJUST → CLOSE

```
1. POST /signal  {"action":"OPEN","source":"bot_manager","symbol":"ETHUSDT","side":"BUY","sl":3201}
   ├─ Valida secret, signal_id (dedup), timestamp (< 5min)
   ├─ Resolve: source="bot_manager" → folder_id="10"
   └─ BackgroundTask: _execute_open()
         ├─ binance_executor.open_position(ETHUSDT, buy, price, sizing)
         ├─ open_positions[("10","ETHUSDT")] = {...}
         ├─ position_id_index["MGR-ETH-001"] = ("10","ETHUSDT")
         └─ Excel: fila PENDING
   ← {"status":"accepted","signal_id":"...","executor_mode":"dry-run"}

2. POST /signal  {"action":"ADJUST","position_id":"MGR-ETH-001","sl":3250}
   └─ BackgroundTask: _execute_adjust()
         ├─ binance_executor.cancel_open_orders(ETHUSDT)
         ├─ Recoloca STOP_MARKET en nuevo SL=3250
         └─ open_positions[("10","ETHUSDT")]["sl"] = 3250

3. POST /signal  {"action":"CLOSE","position_id":"MGR-ETH-001","price":3342}
   └─ BackgroundTask: _execute_close()
         ├─ binance_executor.close_position(ETHUSDT)
         └─ update_excel_result(WIN/LOSS, pnl_pct)
```

---

## 11. Variables de entorno relevantes

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DRY_RUN` | `true` | Simula sin ejecutar en Binance |
| `TV_WEBHOOK_SECRET` | (vacío) | Secret compartido con todos los emisores |
| `BINANCE_API_KEY` | — | API key Binance Futures USDT-M |
| `BINANCE_API_SECRET` | — | API secret Binance Futures USDT-M |
| `BINANCE_TESTNET` | `false` | Usar testnet de Binance |
| `BINANCE_DEFAULT_LEVERAGE` | `10` | Leverage si config.json no lo define |
| `BINANCE_DEFAULT_MARGIN_USDT` | `5.0` | Margen si config.json no lo define |
| `BINANCE_MAX_MARGIN_PCT` | `0.95` | Cap de seguridad: max margen / balance libre |
| `PORT` | `8001` | Puerto del servidor FastAPI |

---

## 12. Logs y registros por carpeta

```
estrategias/estrategia_{id}/
  config.json                         ← config activa (binance_live, sizing, balance_inicial_usdt)
  trade_log_YYYY_MM.xlsx              ← Excel mensual (nuevo archivo cada mes)
  actividades/
    balance.json                      ← balance USDT acumulado (persiste entre reinicios)
    senales_recibidas.jsonl           ← TODA señal recibida (incluso de carpetas disabled)
    ejecuciones.jsonl                 ← toda ejecución open/close
    eventos/{timestamp}.json          ← un JSON por evento (abre/cierra)
```

### Excel mensual (trade_log_YYYY_MM.xlsx)

Columnas: `fecha`, `hora_utc`, `event_id`, `id_carpeta`, `emisor`, `mode`, `symbol`, `side`,
`precio_entrada`, `precio_salida`, `sl`, `tp`, `margen_usdt`, `leverage`, `notional_usdt`,
`order_id`, `binance_status`, `duracion_min`, `resultado`, `pnl_pct`, `profit_usdt`,
`close_reason`, `balance_antes`, `balance_despues`.

Al inicio de cada mes se agrega una fila amarilla con el balance heredado del mes anterior.

### balance.json

```json
{
  "balance": 105.23,
  "initial_balance": 100.0,
  "updated_at": "2026-05-28T22:00:10Z",
  "total_trades": 5,
  "total_profit_usdt": 5.23
}
```

---

## 13. Ir a LIVE (por carpeta)

1. En `estrategias/estrategia_{id}/config.json`: `"binance_live": true` — **hot-reload, sin reinicio**
2. En `sistema/.env`: `DRY_RUN=false`, `BINANCE_TESTNET=false` — **requiere reinicio**
3. Confirmar API keys de Binance Futures con permisos de trading
4. Verificar con `GET /health` que `dry_run_global=false` y la carpeta no aparece en `carpetas_dry_run_local`
5. Probar con señal real — confirmar en `/api/folder/{id}/status` que la posición se registró

**Dos niveles de protección:**
- `DRY_RUN=true` en `.env` → frena TODAS las carpetas globalmente
- `binance_live: false` en `config.json` → frena solo esa carpeta (independiente del global)
