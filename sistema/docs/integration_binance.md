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
2. margin = balance * 0.95      -> 95% del balance (5% reserva para fees)
3. notional = margin * 25       -> leverage x25
4. qty = notional / price       -> redondeado al step_size de Binance
5. futures_change_leverage(25)  -> configura leverage
6. MARKET order (qty)           -> entra al mercado
7. Si sl > 0 y strategy en 5-10: STOP_MARKET -> stop loss
8. Si tp > 0 y strategy en 5-10: TAKE_PROFIT_MARKET -> take profit
```

**Estrategias 1, 2, 3 y 4:** no envian sl/tp (siempre None) — TradingView gestiona cierre via alerta explícita.

**Estrategias 5-10:** si envian sl/tp — el bot los registra como ordenes separadas en Binance y el Price Poller monitorea TP/SL cada 60s.

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
margen             = balance * 0.95            # 95% del balance (5% para fees)
notional           = margen * 25               # leverage x25
qty_raw            = notional / precio_entrada
qty                = redondear_hacia_abajo(qty_raw, step_size_binance)

Ejemplo con $92.43 USDT en SOLUSDT a $85.30:
  margen   = $92.43 * 0.95  = $87.81
  notional = $87.81 * 25    = $2,195.25
  qty_raw  = $2,195.25 / $85.30 = 25.73 SOL
  qty      = 25.7 SOL  (step=0.1)
  margen_real = 25.7 * $85.30 / 25 = $87.70 USDT
```

El balance se consulta en tiempo real antes de cada trade. Si ganas $2, la proxima
orden usa $94.43 — el efecto compuesto es automatico.

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
| BINANCE_MAX_MARGIN_PCT | % del balance a usar por trade (0.95 = 95%, NO 0.99 que causa "Margin is insufficient") |

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
