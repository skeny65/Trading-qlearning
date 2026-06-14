# Schemas de Datos — bot_ejecutor v2

## Estructura de carpetas

```
estrategias/
  estrategia_{1-10}/
    config.json              ← configuracion de la carpeta
    trade_log.xlsx           ← log de trades (Excel)
    INSIGHTS.md              ← metricas legibles
    actividades/
      senales_recibidas.jsonl  ← toda señal recibida
      ejecuciones.jsonl        ← toda ejecucion open/close
      eventos/                 ← {timestamp}.json por evento
      backups/                 ← reservado
```

---

## config.json por carpeta

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
  "notas": "texto libre"
}
```

`symbols_permitidos: []` significa acepta cualquier simbolo.
`binance_live: false` simula sin tocar Binance. Se aplica en la proxima señal sin reiniciar.
`balance_inicial_usdt` define el capital inicial para el tracking de balance acumulado.
```

Valores validos de `modo_cierre`: `dos_senales`, `una_senal_poller`, `sltp_en_binance`.
Valores validos de `emisor`: `tradingview`, `generico`, `bot_grid`, `bot_manager`.

---

## SignalInterna (estructura interna)

```python
{
  "id_carpeta":   "1",
  "tipo":         "open" | "close" | "ignorar",
  "symbol":       "SOLUSDT",
  "side":         "buy" | "sell",
  "price":        155.20,
  "sl":           150.00,      # None si no aplica
  "tp":           165.00,      # None si no aplica
  "entry_price":  None,        # solo en close
  "pnl_pct":      None,        # solo en close
  "close_reason": None,        # solo en close
  "raw":          { ... }      # payload original
}
```

---

## trade_log_YYYY_MM.xlsx — columnas

Un archivo Excel por mes. Nuevo archivo cada mes, con fila inicial amarilla heredando el balance del mes anterior.

| Columna         | Tipo   | Descripcion                              |
|-----------------|--------|------------------------------------------|
| fecha           | str    | YYYY-MM-DD                               |
| hora_utc        | str    | HH:MM:SS                                 |
| event_id        | str    | ID unico del evento                      |
| id_carpeta      | str    | Numero de carpeta (1-10)                 |
| emisor          | str    | tradingview, bot_grid, bot_manager       |
| mode            | str    | DRY_RUN o LIVE                           |
| symbol          | str    | SOLUSDT, ETHUSDT, BTCUSDT, etc.          |
| side            | str    | buy o sell                               |
| precio_entrada  | float  | Precio al abrir                          |
| precio_salida   | float  | PENDING → precio al cerrar               |
| sl              | float  | Stop loss                                |
| tp              | float  | Take profit                              |
| margen_usdt     | float  | Margen USDT comprometido                 |
| leverage        | int    | Apalancamiento                           |
| notional_usdt   | float  | margen × leverage                        |
| order_id        | str    | ID de orden de Binance (o dry_XXX)       |
| binance_status  | str    | ok, skip, error, dry_run                 |
| duracion_min    | float  | PENDING → minutos desde apertura         |
| resultado       | str    | PENDING → WIN o LOSS                     |
| pnl_pct         | str    | PENDING → "+1.45%"                       |
| profit_usdt     | float  | PENDING → ganancia/perdida real en USDT  |
| close_reason    | str    | Motivo de cierre                         |
| balance_antes   | float  | Balance USDT al abrir la posicion        |
| balance_despues | float  | PENDING → balance tras cerrar            |

Colores: verde = WIN, rojo = LOSS, amarillo = fila de balance inicial del mes.

---

## ejecuciones.jsonl — campos clave

```json
{
  "ts":           "2026-05-28T10:30:00.000000+00:00",
  "event_id":     "20260528_103000123456",
  "id_carpeta":   "1",
  "tipo":         "close",
  "symbol":       "SOLUSDT",
  "close_price":  165.00,
  "pnl_pct":      6.31,
  "close_reason": "Cruce contrario",
  "duration_min": 47.0,
  "resultado":    "WIN",
  "order_id":     "dry_SOLUSDT_20260528_102300",
  "mode":         "DRY_RUN"
}
```

El modulo `manager/metrics.py` lee este archivo para calcular winrate y PnL.
