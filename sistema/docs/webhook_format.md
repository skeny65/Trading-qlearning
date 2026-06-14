# Formato de Webhook — bot_ejecutor v2

## Endpoint

```
POST /webhook/{folder_id}    (folder_id: 1-10)
```

Headers opcionales:
- `x-webhook-secret: <TV_WEBHOOK_SECRET>`  (o `?secret=...` en query string)

---

## Emisor: TradingView

### Open (compra o venta)

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

- `action`: `"buy"` | `"sell"` | `"close_buy"` | `"close_sell"` | `"short"` | `"long"`
- `signal_type`: `"open"` | `"close"`
- `params.price`: precio de entrada actual (float)
- `params.sl`: stop loss (opcional)
- `params.tp`: take profit (opcional)

### Close (segunda alerta)

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
      "close_reason": "Cruce contrario"
    }
  }
}
```

- `params.entry_price`: precio de apertura (para calcular PnL si pnl_pct no viene)
- `params.pnl_pct`: porcentaje de ganancia/perdida (opcional, se calcula si no viene)
- `params.close_reason`: texto libre — descripcion del motivo de cierre

### Payload ignorado

Si `status != "pending"`, el bot responde `{"ok": true, "skipped": "..."}` sin ejecutar nada.

---

## Emisor: Generico

Formato minimo:

```json
{
  "tipo": "open",
  "symbol": "BTCUSDT",
  "side": "sell",
  "price": 67000.0,
  "sl": 68500.0,
  "tp": 64000.0
}
```

```json
{
  "tipo": "close",
  "symbol": "BTCUSDT",
  "price": 64000.0,
  "pnl_pct": 4.48,
  "close_reason": "TP_HIT"
}
```

---

## Respuestas del webhook

| Caso                     | HTTP | Body                                         |
|--------------------------|------|----------------------------------------------|
| Exito                    | 200  | `{"ok": true}`                               |
| Carpeta disabled         | 200  | `{"ok": true, "skipped": "disabled"}`        |
| Symbol no permitido      | 200  | `{"ok": true, "skipped": "symbol X no ..."}` |
| Doble open mismo symbol  | 200  | `{"ok": true, "skipped": "posicion ya ..."}` |
| Signal ignorada          | 200  | `{"ok": true, "skipped": "status=ok ..."}`   |
| JSON invalido            | 400  | `{"detail": "JSON invalido"}`                |
| Payload mal formado      | 422  | `{"detail": "Payload invalido: ..."}`        |
| Secret incorrecto        | 401  | `{"detail": "Webhook secret invalido"}`      |
| Carpeta fuera de rango   | 404  | `{"detail": "Carpeta '11' no existe"}`       |
