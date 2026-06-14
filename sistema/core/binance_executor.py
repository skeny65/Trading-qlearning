"""
binance_executor.py - Ejecucion directa de ordenes en Binance Futures USDT-M.

Flujo:
    Emisor -> bot_ejecutor -> Binance Futures

Sizing: determinado por la config de cada carpeta (margen_fijo_usdt + leverage).
No se usa porcentaje del balance total — cada carpeta usa su margen fijo.
"""
import logging
import os
from decimal import Decimal, ROUND_DOWN
from typing import Optional

logger = logging.getLogger("bot3.binance")

_symbol_cache: dict = {}
_client = None


# =============================================================================
# Cliente
# =============================================================================

def get_client():
    global _client
    if _client is None:
        try:
            from binance.client import Client
        except ImportError:
            raise ImportError("Instala python-binance: pip install python-binance")

        api_key    = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet    = os.getenv("BINANCE_TESTNET", "false").lower() in ("1", "true", "yes")

        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY y BINANCE_API_SECRET no definidos en .env")

        _client = Client(api_key, api_secret, testnet=testnet)
        logger.info(f"Binance Futures client inicializado (testnet={testnet})")

    return _client


def is_available() -> bool:
    return bool(os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET"))


# =============================================================================
# Helpers internos
# =============================================================================

def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _get_filters(symbol: str) -> dict:
    if symbol in _symbol_cache:
        return _symbol_cache[symbol]

    client = get_client()
    info   = client.futures_exchange_info()
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            f = {x["filterType"]: x for x in s["filters"]}
            _symbol_cache[symbol] = {
                "step":         Decimal(f["LOT_SIZE"]["stepSize"]),
                "tick":         Decimal(f["PRICE_FILTER"]["tickSize"]),
                "min_qty":      Decimal(f["LOT_SIZE"]["minQty"]),
                "min_notional": Decimal(
                    f.get("MIN_NOTIONAL", {}).get("notional",
                    f.get("NOTIONAL", {}).get("minNotional", "5"))
                ),
            }
            return _symbol_cache[symbol]
    raise ValueError(f"Simbolo no encontrado en Binance Futures: {symbol}")


def _emergency_close(symbol: str, close_side: str, qty: Decimal) -> None:
    try:
        from binance.exceptions import BinanceAPIException
        client = get_client()
        client.futures_create_order(
            symbol=symbol, side=close_side, type="MARKET",
            quantity=str(qty), reduceOnly=True,
        )
        logger.info(f"[{symbol}] Emergency close ejecutado (qty={qty})")
    except Exception as ex:
        logger.error(f"[{symbol}] Emergency close FALLO: {ex}")


# =============================================================================
# Consultas de cuenta
# =============================================================================

def get_usdt_balance() -> float:
    client = get_client()
    for b in client.futures_account_balance():
        if b["asset"] == "USDT":
            return float(b["availableBalance"])
    return 0.0


def get_position_qty(symbol: str) -> float:
    client = get_client()
    for p in client.futures_position_information(symbol=symbol):
        amt = float(p["positionAmt"])
        if amt != 0:
            return amt
    return 0.0


def has_open_position(symbol: str) -> bool:
    return get_position_qty(symbol) != 0


def cancel_open_orders(symbol: str) -> None:
    try:
        client = get_client()
        client.futures_cancel_all_open_orders(symbol=symbol)
        logger.info(f"[{symbol}] Ordenes abiertas canceladas")
    except Exception as e:
        logger.warning(f"[{symbol}] Error cancelando ordenes: {e}")


# =============================================================================
# Apertura de posicion
# =============================================================================

def open_position(
    symbol:     str,
    side:       str,
    price:      float,
    sizing_cfg: dict,
    sl:         Optional[float] = None,
    tp:         Optional[float] = None,
) -> dict:
    """
    Abre posicion en Binance Futures USDT-M usando el sizing de la carpeta.

    sizing_cfg: {"tipo": "margen_fijo_usdt", "margen_usdt": 5.0, "leverage": 10}

    Retorna:
        {"status": "ok"|"skip"|"error", "order_id": str, "detail": str, "qty": float, "margen_usdt": float}
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    leverage    = int(sizing_cfg.get("leverage", 10))
    margen_usdt = float(sizing_cfg.get("margen_usdt", 5.0))

    b_side  = "BUY"  if side == "buy"  else "SELL"
    cl_side = "SELL" if b_side == "BUY" else "BUY"

    # Validar balance suficiente para cubrir el margen requerido
    try:
        balance = get_usdt_balance()
    except Exception as e:
        return {"status": "error", "detail": f"Error consultando balance: {e}"}

    max_margin_pct = float(os.getenv("BINANCE_MAX_MARGIN_PCT", "0.95"))
    if margen_usdt > balance * max_margin_pct:
        return {
            "status": "skip",
            "detail": f"Balance insuficiente: ${balance:.2f} disponible, margen requerido=${margen_usdt:.2f}",
        }

    # Filtros del simbolo
    try:
        filt = _get_filters(symbol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    # Calcular cantidad: notional = margen * leverage
    notional_target = Decimal(str(margen_usdt)) * Decimal(str(leverage))
    qty_raw = notional_target / Decimal(str(price))
    qty     = _round_down(qty_raw, filt["step"])

    if qty < filt["min_qty"]:
        return {"status": "skip", "detail": f"qty {qty} < minQty {filt['min_qty']}"}

    notional = qty * Decimal(str(price))
    if notional < filt["min_notional"]:
        return {"status": "skip", "detail": f"notional {float(notional):.2f} < min {float(filt['min_notional']):.2f}"}

    if has_open_position(symbol):
        return {"status": "skip", "detail": f"{symbol} ya tiene una posicion abierta"}

    client = get_client()

    try:
        client.futures_change_margin_type(symbol=symbol, marginType="CROSSED")
        logger.info(f"[{symbol}] Margen: CROSSED")
    except Exception as e:
        # Binance lanza error si ya está en CROSSED — se ignora
        if "No need to change margin type" not in str(e):
            logger.warning(f"[{symbol}] setMarginType: {e}")

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logger.info(f"[{symbol}] Leverage: {leverage}x")
    except Exception as e:
        logger.warning(f"[{symbol}] setLeverage: {e}")

    # Orden de entrada MARKET
    try:
        from binance.exceptions import BinanceAPIException
        entry_order = client.futures_create_order(
            symbol=symbol, side=b_side, type="MARKET", quantity=str(qty),
        )
    except BinanceAPIException as e:
        return {"status": "error", "detail": f"MARKET entry: {e.message}"}

    order_id = str(entry_order.get("orderId", ""))
    logger.info(
        f"[{symbol}] MARKET {b_side} qty={qty} "
        f"margen=${margen_usdt:.2f} leverage={leverage}x order_id={order_id}"
    )

    # Stop Loss (solo si se proporciona)
    if sl and sl > 0:
        try:
            from binance.exceptions import BinanceAPIException
            sl_px = _round_down(Decimal(str(sl)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="STOP_MARKET",
                stopPrice=str(sl_px), closePosition=True,
                workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] SL colocado en {sl_px}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] SL fallo: {e.message} — cerrando posicion")
            _emergency_close(symbol, cl_side, qty)
            return {"status": "error", "detail": f"SL: {e.message}"}

    # Take Profit (solo si se proporciona)
    if tp and tp > 0:
        try:
            from binance.exceptions import BinanceAPIException
            tp_px = _round_down(Decimal(str(tp)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(tp_px), closePosition=True,
                workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] TP colocado en {tp_px}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] TP fallo (posicion con SL activo): {e.message}")

    return {
        "status":      "ok",
        "order_id":    order_id,
        "qty":         float(qty),
        "margen_usdt": margen_usdt,
        "detail":      f"qty={qty} margen=${margen_usdt:.2f} lev={leverage}x",
    }


# =============================================================================
# Apertura por riesgo fijo (BOT_GRID / TradingView risk-sizing — carpeta 1)
# =============================================================================

def open_position_by_risk(
    symbol:   str,
    side:     str,
    qty:      float,
    sl:       float,
    tp:       Optional[float],
    leverage: int = 25,
) -> dict:
    """
    Abre posición con qty exacta ya calculada por riesgo fijo.

    Orden de operaciones (crítico):
      1. CROSSED margin + leverage
      2. MARKET order  (abre posición)
      3. STOP_MARKET   (SL) — si falla → emergency close (rollback)
      4. TAKE_PROFIT_MARKET (TP) — si falla → warning, SL ya protege

    Args:
        qty: cantidad calculada externamente por calcular_qty_por_riesgo().
        sl:  precio del stop loss.
        tp:  precio del take profit (None = sin TP).
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    b_side  = "BUY"  if side == "buy"  else "SELL"
    cl_side = "SELL" if b_side == "BUY" else "BUY"

    try:
        filt = _get_filters(symbol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    client = get_client()

    # 1. Margen CROSSED + leverage
    try:
        client.futures_change_margin_type(symbol=symbol, marginType="CROSSED")
        logger.info(f"[{symbol}] Margen: CROSSED")
    except Exception as e:
        if "No need to change margin type" not in str(e):
            logger.warning(f"[{symbol}] setMarginType: {e}")

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logger.info(f"[{symbol}] Leverage: {leverage}x")
    except Exception as e:
        logger.warning(f"[{symbol}] setLeverage: {e}")

    # 2. Orden MARKET
    try:
        entry_order = client.futures_create_order(
            symbol=symbol, side=b_side, type="MARKET", quantity=str(qty),
        )
        order_id = str(entry_order.get("orderId", ""))
        logger.info(f"[{symbol}] MARKET {b_side} qty={qty} order_id={order_id}")
    except BinanceAPIException as e:
        return {"status": "error", "detail": f"MARKET entry: {e.message}"}

    # 3. Stop Loss — si falla, cerrar posición (rollback)
    try:
        sl_px = _round_down(Decimal(str(sl)), filt["tick"])
        client.futures_create_order(
            symbol=symbol, side=cl_side, type="STOP_MARKET",
            stopPrice=str(sl_px), closePosition=True,
            workingType="MARK_PRICE",
        )
        logger.info(f"[{symbol}] SL colocado en {sl_px}")
    except BinanceAPIException as e:
        logger.error(f"[{symbol}] SL FALLO: {e.message} — cerrando posicion (rollback)")
        _emergency_close(symbol, cl_side, Decimal(str(qty)))
        return {"status": "error", "detail": f"SL fallo, posicion cerrada: {e.message}"}

    # 4. Take Profit — fallo no hace rollback (SL ya activo)
    if tp and tp > 0:
        try:
            tp_px = _round_down(Decimal(str(tp)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(tp_px), closePosition=True,
                workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] TP colocado en {tp_px}")
        except BinanceAPIException as e:
            logger.warning(f"[{symbol}] TP fallo (SL activo, posicion protegida): {e.message}")

    return {
        "status":   "ok",
        "order_id": order_id,
        "qty":      qty,
        "detail":   f"qty={qty} lev={leverage}x sl={sl} tp={tp}",
    }


# =============================================================================
# Cierre de posicion
# =============================================================================

def place_trailing_stop(symbol: str, side: str, callback_rate: float, qty: float) -> dict:
    """
    Coloca TRAILING_STOP_MARKET para cerrar automaticamente una posicion abierta.

    Args:
        side:          direccion de la posicion abierta ("buy" o "sell")
        callback_rate: porcentaje de retroceso, p.ej. 2.1 para 2.1%
        qty:           cantidad exacta abierta (de open_position resultado["qty"])
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    cl_side = "SELL" if side == "buy" else "BUY"

    try:
        filt = _get_filters(symbol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    qty_dec = _round_down(Decimal(str(qty)), filt["step"])
    # Binance: callbackRate min=0.1, max=5.0, maximo 1 decimal
    cb_str = str(max(round(callback_rate, 1), 0.1))

    client = get_client()
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=cl_side,
            type="TRAILING_STOP_MARKET",
            callbackRate=cb_str,
            quantity=str(qty_dec),
            workingType="CONTRACT_PRICE",
            reduceOnly=True,
        )
        order_id = str(order.get("orderId", ""))
        logger.info(f"[{symbol}] Trailing stop OK: callback={cb_str}% qty={qty_dec} id={order_id}")
        return {
            "status":        "ok",
            "order_id":      order_id,
            "callback_rate": float(cb_str),
            "detail":        f"trailing callback={cb_str}% qty={qty_dec}",
        }
    except BinanceAPIException as e:
        logger.error(f"[{symbol}] Trailing stop fallo: {e.message}")
        return {"status": "error", "detail": e.message}
    except Exception as e:
        logger.error(f"[{symbol}] Trailing stop error inesperado: {e}")
        return {"status": "error", "detail": str(e)}


def close_position(symbol: str) -> dict:
    """
    Cierra la posicion abierta del simbolo:
      1. Cancela todas las ordenes abiertas (SL/TP pendientes)
      2. MARKET reduceOnly por la cantidad real de la posicion
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    cancel_open_orders(symbol)

    qty_amt = get_position_qty(symbol)
    if qty_amt == 0:
        logger.warning(f"[{symbol}] close_position: no hay posicion abierta")
        return {"status": "skip", "detail": "sin posicion abierta en Binance"}

    close_side = "SELL" if qty_amt > 0 else "BUY"
    qty        = abs(qty_amt)

    client = get_client()
    try:
        order    = client.futures_create_order(
            symbol=symbol, side=close_side, type="MARKET",
            quantity=str(qty), reduceOnly=True,
        )
        order_id = str(order.get("orderId", ""))
        logger.info(f"[{symbol}] CLOSE MARKET {close_side} qty={qty} order_id={order_id}")
        return {"status": "ok", "order_id": order_id, "detail": f"cerrado qty={qty}"}
    except BinanceAPIException as e:
        logger.error(f"[{symbol}] close_position error: {e.message}")
        return {"status": "error", "detail": e.message}


# =============================================================================
# Grid trading (BOT_GRID integration — carpeta 9)
# =============================================================================

def open_grid(
    symbol:     str,
    side:       str,
    params:     dict,
    sizing_cfg: dict,
) -> dict:
    """
    Coloca N limit orders para grid trading en Binance Futures USDT-M.

    params: price_base, range_lower, range_upper, num_levels, sl, tp (opcional)
    side:   "buy" → ordenes LIMIT BUY entre range_lower y price_base
            "sell" → ordenes LIMIT SELL entre price_base y range_upper
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    leverage    = int(sizing_cfg.get("leverage", 10))
    margen_usdt = float(sizing_cfg.get("margen_usdt", 5.0))

    price_base  = float(params.get("price_base", 0))
    range_lower = float(params.get("range_lower") or price_base * 0.95)
    range_upper = float(params.get("range_upper") or price_base * 1.05)
    num_levels  = max(1, int(params.get("num_levels", 3)))
    sl          = params.get("sl")
    tp          = params.get("tp")

    b_side  = "BUY"  if side == "buy"  else "SELL"
    cl_side = "SELL" if b_side == "BUY" else "BUY"

    try:
        filt = _get_filters(symbol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    total_notional     = Decimal(str(margen_usdt)) * Decimal(str(leverage))
    notional_per_level = total_notional / Decimal(str(num_levels))

    if b_side == "BUY":
        step   = (price_base - range_lower) / num_levels
        levels = [range_lower + step * i for i in range(num_levels)]
    else:
        step   = (range_upper - price_base) / num_levels
        levels = [price_base + step * (i + 1) for i in range(num_levels)]

    client = get_client()

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except Exception as e:
        logger.warning(f"[{symbol}] setLeverage grid: {e}")

    order_ids = []
    for px in levels:
        px_dec  = _round_down(Decimal(str(px)), filt["tick"])
        qty_dec = _round_down(notional_per_level / px_dec, filt["step"])

        if qty_dec < filt["min_qty"]:
            logger.warning(f"[{symbol}] Grid nivel px={px_dec} qty={qty_dec} < minQty — skip")
            continue

        try:
            order = client.futures_create_order(
                symbol=symbol, side=b_side, type="LIMIT",
                price=str(px_dec), quantity=str(qty_dec),
                timeInForce="GTC",
            )
            order_ids.append(str(order.get("orderId", "")))
            logger.info(f"[{symbol}] Grid LIMIT {b_side} qty={qty_dec} px={px_dec}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] Grid nivel px={px_dec}: {e.message}")

    if not order_ids:
        return {"status": "error", "detail": "Sin ordenes colocadas en el grid"}

    if sl and sl > 0:
        try:
            sl_dec = _round_down(Decimal(str(sl)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="STOP_MARKET",
                stopPrice=str(sl_dec), closePosition=True,
                workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] Grid SL en {sl_dec}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] Grid SL fallo: {e.message}")

    if tp and tp > 0:
        try:
            tp_dec = _round_down(Decimal(str(tp)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(tp_dec), closePosition=True,
                workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] Grid TP en {tp_dec}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] Grid TP fallo: {e.message}")

    return {
        "status":    "ok",
        "order_id":  order_ids[0],
        "order_ids": order_ids,
        "detail":    f"grid {num_levels} niveles, {len(order_ids)} ordenes colocadas",
    }


def adjust_grid(symbol: str, params: dict, sizing_cfg: dict) -> dict:
    """Cancela ordenes limite abiertas y recoloca el grid con nuevos params."""
    cancel_open_orders(symbol)
    side = params.get("side", "buy")
    return open_grid(symbol, side, params, sizing_cfg)


def close_grid_position(symbol: str) -> dict:
    """Cancela todas las ordenes abiertas y cierra la posicion en Binance."""
    cancel_open_orders(symbol)
    return close_position(symbol)
