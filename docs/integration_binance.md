# Integracion con Binance Futures — bot3-qlearning

## Arquitectura

```
TradingView
    |
    |  POST /webhook/strategy/{id}
    v
bot3.py (localhost:8001)
    |
    |  python-binance SDK
    v
core/binance_executor.py
    |
    |  HTTPS — Binance Futures API (USDT-M)
    v
Binance Futures
```

Ejecucion directa sin intermediarios. La latencia es la de la red hacia Binance.

---

## Modulo: `core/binance_executor.py`

### `open_position(symbol, side, price, sl, tp)`

Abre una posicion en Binance Futures con todo el balance disponible.

```
1. get_usdt_balance()           -> consulta balance USDT en tiempo real
2. margin = balance * 0.99      -> 99% del balance (1% reserva para fees)
3. notional = margin * 25       -> leverage x25
4. qty = notional / price       -> redondeado al step_size de Binance
5. futures_change_leverage(25)  -> configura leverage
6. MARKET order (qty)           -> entra al mercado
7. Si sl > 0: STOP_MARKET       -> stop loss
8. Si tp > 0: TAKE_PROFIT_MARKET -> take profit
```

**Estrategias 1 y 4:** no envian sl/tp — TradingView gestiona SL/TP/trailing internamente.

**Estrategias 5-10:** si envian sl/tp — el bot los registra como ordenes separadas en Binance.

### `close_position(symbol)`

Cierra la posicion completa.

```
1. cancel_open_orders(symbol)   -> cancela SL/TP colgados
2. get_position_qty(symbol)     -> consulta qty real en Binance
3. MARKET order reduceOnly      -> cierre total
```

### `get_usdt_balance()`

Retorna el balance USDT disponible en la cuenta de Futuros (wallet + unrealized PnL).

---

## Calculo de cantidad (automatico)

```
balance_disponible = get_usdt_balance()        # consulta en vivo antes de cada trade
margen             = balance * 0.99            # 99% del balance (1% para fees)
notional           = margen * 25               # leverage x25
qty_raw            = notional / precio_entrada
qty                = redondear_hacia_abajo(qty_raw, step_size_binance)

Ejemplo con $17.54 USDT en SOLUSDT a $87.37:
  margen   = $17.54 * 0.99  = $17.36
  notional = $17.36 * 25    = $434.09
  qty_raw  = $434.09 / $87.37 = 4.967 SOL
  qty      = 4.9 SOL  (step=0.1)
  margen_real = 4.9 * $87.37 / 25 = $17.12 USDT
```

El balance se consulta en tiempo real antes de cada trade. Si ganas $2, la proxima
orden usa $19.54 — el efecto compuesto es automatico.

---

## Variables de entorno

```env
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_API_SECRET=tu_api_secret_aqui
BINANCE_TESTNET=false
BINANCE_LEVERAGE=25
BINANCE_MAX_MARGIN_PCT=0.99
```

| Variable             | Descripcion                                       |
|----------------------|---------------------------------------------------|
| BINANCE_API_KEY      | API Key con permisos de Futuros                   |
| BINANCE_API_SECRET   | API Secret                                        |
| BINANCE_TESTNET      | `true` = testnet (paper trading sin dinero real)  |
| BINANCE_LEVERAGE     | Apalancamiento (x25 por defecto)                  |
| BINANCE_MAX_MARGIN_PCT | % del balance a usar por trade (0.99 = 99%)    |

---

## Estrategias y su modo de ejecucion

| ID   | Par     | Ejecucion  | Cierre                               |
|------|---------|------------|--------------------------------------|
| 1    | SOLUSDT | LIVE       | Alerta close TradingView → inmediato |
| 2    | SOLUSDT | LEARN ONLY | Alerta close TradingView → inmediato |
| 3    | SOLUSDT | LEARN ONLY | Alerta close TradingView → inmediato |
| 4    | ETHUSDT | LIVE       | Alerta close TradingView → inmediato |
| 5-10 | varios  | LIVE       | Price Poller Binance cada 60s        |

**LEARN ONLY (estrategias 2 y 3):** reciben senales reales de TradingView y
aprenden de ellas, pero NO ejecutan ordenes en Binance. Util para acumular
experiencia con senales reales sin arriesgar capital.

---

## Tipos de ordenes utilizadas

| Tipo                 | Cuando                                    |
|----------------------|-------------------------------------------|
| MARKET               | Entrada de posicion                       |
| MARKET reduceOnly    | Cierre de posicion                        |
| STOP_MARKET          | Stop Loss (solo estrategias 5-10)         |
| TAKE_PROFIT_MARKET   | Take Profit (solo estrategias 5-10)       |

---

## Permisos requeridos en la API Key de Binance

- **Enable Futures** — obligatorio
- **Enable Reading** — para consultar balance y posiciones
- **Enable Spot & Margin Trading** — no requerido
- **Restrict access to trusted IPs** — recomendado en produccion

---

## Verificar conectividad

```powershell
# Ping a Binance (sin key)
Invoke-WebRequest https://api.binance.com/api/v3/ping

# Verificar balance (con key configurada en .env)
# Se puede ver en el health check del bot:
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content
```
