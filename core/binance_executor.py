"""
binance_executor.py - Ejecucion directa de ordenes en Binance Futures USDT-M.

Reemplaza a bot1 como destino de las senales. Flujo:
    TradingView -> bot3 (Q-Learning) -> Binance Futures

Variables requeridas en .env:
    BINANCE_API_KEY
    BINANCE_API_SECRET
    BINANCE_TESTNET       (false por defecto)
    BINANCE_LEVERAGE      (10 por defecto)
    BINANCE_MARGIN_USDT   (5 por defecto — margen por operacion)
    BINANCE_MAX_MARGIN_PCT (0.80 por defecto)
"""
import logging
import os
from decimal import Decimal, ROUND_DOWN
from typing import Optional

logger = logging.getLogger("bot3.binance")

# Cache de filtros por simbolo para no llamar exchange_info en cada orden
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
    """True si las credenciales estan configuradas."""
    return bool(os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET"))


# =============================================================================
# Helpers internos
# =============================================================================

def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _get_filters(symbol: str) -> dict:
    """Obtiene step size, tick size y minimo notional del simbolo."""
    if symbol in _symbol_cache:
        return _symbol_cache[symbol]

    client = get_client()
    info   = client.futures_exchange_info()
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            f = {x["filterType"]: x for x in s["filters"]}
            _symbol_cache[symbol] = {
                "step":        Decimal(f["LOT_SIZE"]["stepSize"]),
                "tick":        Decimal(f["PRICE_FILTER"]["tickSize"]),
                "min_qty":     Decimal(f["LOT_SIZE"]["minQty"]),
                "min_notional": Decimal(
                    f.get("MIN_NOTIONAL", {}).get("notional",
                    f.get("NOTIONAL", {}).get("minNotional", "5"))
                ),
            }
            return _symbol_cache[symbol]
    raise ValueError(f"Simbolo no encontrado en Binance Futures: {symbol}")


def _emergency_close(symbol: str, close_side: str, qty: Decimal) -> None:
    """Cierra posicion de emergencia cuando SL/TP fallan al colocarse."""
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
    """Balance USDT disponible en Futuros."""
    client = get_client()
    for b in client.futures_account_balance():
        if b["asset"] == "USDT":
            return float(b["availableBalance"])
    return 0.0


def get_position_qty(symbol: str) -> float:
    """positionAmt de la posicion abierta (+ = long, - = short, 0 = sin posicion)."""
    client = get_client()
    for p in client.futures_position_information(symbol=symbol):
        amt = float(p["positionAmt"])
        if amt != 0:
            return amt
    return 0.0


def has_open_position(symbol: str) -> bool:
    return get_position_qty(symbol) != 0


def cancel_open_orders(symbol: str) -> None:
    """Cancela todas las ordenes abiertas del simbolo (SL/TP colgados)."""
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
    symbol: str,
    side:   str,           # "buy" o "sell"
    price:  float,         # precio actual (para calcular qty)
    sl:     Optional[float] = None,
    tp:     Optional[float] = None,
) -> dict:
    """
    Abre posicion en Binance Futures USDT-M:
      1. MARKET (entrada inmediata)
      2. STOP_MARKET closePosition=True (SL, si se proporciona)
      3. TAKE_PROFIT_MARKET closePosition=True (TP, si se proporciona)

    Retorna:
        {"status": "ok"|"skip"|"error", "order_id": str, "detail": str}
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    # Parametros desde .env
    leverage       = int(os.getenv("BINANCE_LEVERAGE",         "10"))
    max_margin_pct = float(os.getenv("BINANCE_MAX_MARGIN_PCT", "0.95"))

    b_side  = "BUY"  if side == "buy"  else "SELL"
    cl_side = "SELL" if b_side == "BUY" else "BUY"

    # Balance disponible — usar todo (con cap de seguridad)
    balance = get_usdt_balance()
    if balance <= 0:
        return {"status": "error", "detail": f"balance USDT = {balance}"}

    margin_usdt = balance * max_margin_pct
    logger.info(f"[{symbol}] Balance disponible: ${balance:.2f} → margen a usar: ${margin_usdt:.2f}")

    # Filtros del simbolo
    try:
        filt = _get_filters(symbol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    # Calcular cantidad: notional = margen * leverage / precio
    notional_target = Decimal(str(margin_usdt)) * Decimal(str(leverage))
    qty_raw = notional_target / Decimal(str(price))
    qty     = _round_down(qty_raw, filt["step"])

    if qty < filt["min_qty"]:
        return {"status": "skip", "detail": f"qty {qty} < minQty {filt['min_qty']}"}

    notional = qty * Decimal(str(price))
    if notional < filt["min_notional"]:
        return {"status": "skip", "detail": f"notional {float(notional):.2f} < min {float(filt['min_notional']):.2f}"}

    margin_req = float(notional) / leverage

    # No abrir si ya hay posicion abierta en ese simbolo
    if has_open_position(symbol):
        return {"status": "skip", "detail": f"{symbol} ya tiene una posicion abierta"}

    client = get_client()

    # Configurar leverage
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except BinanceAPIException as e:
        logger.warning(f"[{symbol}] setLeverage: {e.message}")

    # --- Orden de entrada MARKET ---
    try:
        entry_order = client.futures_create_order(
            symbol=symbol, side=b_side, type="MARKET", quantity=str(qty),
        )
    except BinanceAPIException as e:
        return {"status": "error", "detail": f"MARKET entry: {e.message}"}

    order_id = str(entry_order.get("orderId", ""))
    logger.info(
        f"[{symbol}] MARKET {b_side} qty={qty} "
        f"margen=${margin_req:.2f} leverage={leverage}x order_id={order_id}"
    )

    # --- Stop Loss ---
    if sl and sl > 0:
        try:
            sl_px = _round_down(Decimal(str(sl)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="STOP_MARKET",
                stopPrice=str(sl_px), closePosition=True,
                timeInForce="GTC", workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] SL colocado en {sl_px}")
        except BinanceAPIException as e:
            logger.error(f"[{symbol}] SL fallo: {e.message} — cerrando posicion")
            _emergency_close(symbol, cl_side, qty)
            return {"status": "error", "detail": f"SL: {e.message}"}

    # --- Take Profit ---
    if tp and tp > 0:
        try:
            tp_px = _round_down(Decimal(str(tp)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(tp_px), closePosition=True,
                timeInForce="GTC", workingType="MARK_PRICE",
            )
            logger.info(f"[{symbol}] TP colocado en {tp_px}")
        except BinanceAPIException as e:
            # TP falla pero SL ya esta puesto — posicion protegida, no es emergencia
            logger.error(f"[{symbol}] TP fallo (posicion con SL activo): {e.message}")

    return {
        "status":   "ok",
        "order_id": order_id,
        "detail":   f"qty={qty} margen=${margin_req:.2f} lev={leverage}x",
    }


# =============================================================================
# Cierre de posicion
# =============================================================================

def close_position(symbol: str) -> dict:
    """
    Cierra la posicion abierta del simbolo:
      1. Cancela todas las ordenes abiertas (SL/TP pendientes)
      2. MARKET reduceOnly por la cantidad real de la posicion

    Retorna:
        {"status": "ok"|"skip"|"error", "order_id": str, "detail": str}
    """
    try:
        from binance.exceptions import BinanceAPIException
    except ImportError:
        return {"status": "error", "detail": "python-binance no instalado"}

    # Cancelar ordenes SL/TP que aun esten pendientes
    cancel_open_orders(symbol)

    # Obtener cantidad real de la posicion
    qty_amt = get_position_qty(symbol)
    if qty_amt == 0:
        logger.warning(f"[{symbol}] close_position: no hay posicion abierta")
        return {"status": "skip", "detail": "sin posicion abierta en Binance"}

    close_side = "SELL" if qty_amt > 0 else "BUY"
    qty        = abs(qty_amt)

    client = get_client()
    try:
        order = client.futures_create_order(
            symbol=symbol, side=close_side, type="MARKET",
            quantity=str(qty), reduceOnly=True,
        )
        order_id = str(order.get("orderId", ""))
        logger.info(f"[{symbol}] CLOSE MARKET {close_side} qty={qty} order_id={order_id}")
        return {"status": "ok", "order_id": order_id, "detail": f"cerrado qty={qty}"}
    except BinanceAPIException as e:
        logger.error(f"[{symbol}] close_position error: {e.message}")
        return {"status": "error", "detail": e.message}
