# Flujo End-to-End — bot_ejecutor v2

## Flujo: TradingView → Open → Close (dos_senales)

```
1. TradingView dispara alerta OPEN
      POST /webhook/1
      {"status":"pending","signal":{"signal_type":"open",...}}

2. bot3.py
   ├─ Valida secret / IP
   ├─ Carga config.json de carpeta 1
   ├─ adapter_tradingview.parse() → SignalInterna {tipo="open"}
   ├─ Log → senales_recibidas.jsonl
   ├─ Check: carpeta enabled? Si / No → {skipped}
   ├─ Check: symbol permitido?
   ├─ Check: posicion ya abierta? Si → {skipped}
   └─ BackgroundTask: _execute_open()
         │
         ├─ DRY_RUN: simula order_id
         │  LIVE: binance_executor.open_position()
         │        → MARKET buy/sell
         │        → SL/TP si coloca_sltp_en_binance=true
         │
         ├─ open_positions[(1, "SOLUSDT")] = {...}
         ├─ Excel: fila PENDING
         └─ ejecuciones.jsonl + eventos/{ts}.json

   return {"ok": true}  ← TradingView recibe en < 5s

3. TradingView dispara alerta CLOSE
      POST /webhook/1
      {"status":"pending","signal":{"signal_type":"close",...}}

4. bot3.py
   └─ BackgroundTask: _execute_close()
         │
         ├─ open_pos = open_positions.pop((1, "SOLUSDT"))
         ├─ pnl_pct = calc si no vino en payload
         ├─ DRY_RUN: log / LIVE: binance_executor.close_position()
         ├─ update_excel_result(order_id, "WIN"/"LOSS", pnl_pct)
         ├─ pending_poller.pop(order_id)
         └─ ejecuciones.jsonl + eventos/{ts}.json
```

## Flujo: una_senal_poller

```
1. Señal OPEN entra por /webhook/{id}
   → _execute_open() → pending_poller[order_id] = {...}

2. PricePoller (cada 60s)
   ├─ GET https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT
   ├─ Si current >= tp → close("TP")
   ├─ Si current <= sl → close("SL")
   └─ Si duracion > 24h → close("EXPIRED")
         │
         └─ update_excel_result(...)

3. Señal CLOSE de TradingView NO es necesaria
   (aunque si llega, se procesa igual)
```

## Sizing

```
notional_target = margen_usdt * leverage
qty_raw         = notional_target / price
qty             = round_down(qty_raw, step_size)

Ejemplo: margen=5 USDT, leverage=10x, price=155.20 SOLUSDT
  notional = 50 USDT
  qty_raw  = 50 / 155.20 = 0.3221...
  step     = 0.01 → qty = 0.32 SOL
```

## Condiciones de skip (sin ejecutar)

| Condicion                        | Respuesta                         |
|----------------------------------|-----------------------------------|
| Carpeta disabled                 | `{"skipped": "disabled"}`         |
| status != "pending"              | `{"skipped": "status=ok ..."}`    |
| Symbol no en symbols_permitidos  | `{"skipped": "symbol X no ..."}` |
| Posicion ya abierta (mismo sym)  | `{"skipped": "posicion ya ..."}` |
| Balance insuficiente (LIVE)      | `{"skipped": "Balance insuf..."}` |
| qty < minQty de Binance (LIVE)   | `{"skipped": "qty X < minQty"}` |
