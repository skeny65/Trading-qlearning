# Arquitectura — bot_ejecutor v2

## Principio

Router de ejecucion puro. Sin Q-Learning. Sin decision propia.
Si llega `signal_type=open` → abre. Si llega `signal_type=close` → cierra.

## Flujo de datos

```
Emisor (TradingView, bot_grid, bot_manager, generico)
    │
    │  POST /webhook/{folder_id}
    ▼
bot3.py — FastAPI
    │
    ├─ 1. Validar secret + IP
    ├─ 2. Cargar config de carpeta (folder_config.py)
    ├─ 3. Parsear payload (adapter por emisor)
    ├─ 4. Loguear señal cruda → senales_recibidas.jsonl
    ├─ 5. Si carpeta disabled → return {skipped}
    ├─ 6. Si tipo=open → BackgroundTask: _execute_open()
    └─ 7. Si tipo=close → BackgroundTask: _execute_close()
                │
                ▼
         binance_executor.py
         MARKET open / MARKET close (reduceOnly)
                │
                ▼
         excel_logger.py
         append_excel_row / update_excel_result
                │
                ▼
         ejecuciones.jsonl + eventos/{ts}.json
```

## Modo de cierre por carpeta

| modo_cierre        | Quien cierra          | Price Poller |
|--------------------|----------------------|--------------|
| dos_senales        | TradingView (alerta) | NO           |
| una_senal_poller   | Price Poller (60s)   | SI           |
| sltp_en_binance    | Binance (SL/TP OCO)  | SI (backup)  |

## Sizing por carpeta

Cada `config.json` define `sizing.margen_usdt` y `sizing.leverage`.

```
notional = margen_usdt * leverage
qty      = notional / price
```

Las 10 carpetas son completamente independientes en capital.
No hay riesgo de que una carpeta consuma el balance de otra.

## Componentes principales

| Archivo                        | Rol                                      |
|-------------------------------|------------------------------------------|
| `bot3.py`                      | App FastAPI + rutas + estado global       |
| `core/binance_executor.py`    | MARKET open/close en Binance Futures      |
| `core/folder_config.py`       | Lee y valida config.json por carpeta      |
| `core/adapters/`              | Parser por tipo de emisor                 |
| `manager/price_poller.py`     | Hilo que monitorea TP/SL (60s)           |
| `manager/metrics.py`          | Estadisticas descriptivas por carpeta     |
| `utils/excel_logger.py`       | Log en trade_log.xlsx                     |
| `utils/telegram_notifier.py`  | Notificaciones opcionales                 |

## Estado global (en memoria)

```python
open_positions: dict  # {(folder_id, symbol): {order_id, side, entry_price, ...}}
pending_poller: dict  # {order_id: {folder_id, symbol, sl, tp, ...}}
```

Riesgo: se pierden en reinicios. Mejora futura: persistir a JSONL.
