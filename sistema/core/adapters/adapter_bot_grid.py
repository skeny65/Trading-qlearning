"""
adapter_bot_grid.py - Adaptador para señales BOT_GRID v2.0 (carpeta 9).

Soporta dos formatos:
  1. BOT_GRID v2.0: {version, signal_id, action, symbol, params, ...}
     Acciones: OPEN_GRID → tipo=open, CLOSE_GRID → tipo=close, ADJUST_GRID → tipo=ignorar
  2. Formato generico simple: {tipo, symbol, side, price, sl, tp} (fallback/tests)

El canal primario es JSONL file polling (BotGridPoller).
Este adapter solo se usa si BOT_GRID envia via HTTP POST a /webhook/9.
"""


def parse(body: dict, folder_id: str) -> dict:
    if body.get("version") == "2.0" and "action" in body:
        return _parse_v2(body)
    from core.adapters.adapter_generico import parse as _parse_generico
    return _parse_generico(body, folder_id)


def _parse_v2(body: dict) -> dict:
    action = body.get("action", "").upper()
    symbol = body.get("symbol", "")
    params = body.get("params", {})

    if not symbol:
        raise ValueError("Campo 'symbol' requerido")

    if action == "OPEN_GRID":
        if not params.get("price_base"):
            raise ValueError("OPEN_GRID requiere params.price_base")
        return {
            "tipo":        "open",
            "symbol":      symbol,
            "side":        params.get("side", "buy"),
            "price":       float(params["price_base"]),
            "sl":          params.get("sl"),
            "tp":          params.get("tp"),
            "signal_id":   body.get("signal_id", ""),
            "num_levels":  params.get("num_levels", 3),
            "range_lower": params.get("range_lower"),
            "range_upper": params.get("range_upper"),
            "_raw_action": action,
        }

    if action == "CLOSE_GRID":
        return {
            "tipo":         "close",
            "symbol":       symbol,
            "price":        float(params.get("price_exit", 0)),
            "pnl_pct":      params.get("pnl_pct"),
            "close_reason": params.get("close_reason", "CLOSE_GRID"),
            "signal_id":    body.get("signal_id", ""),
        }

    if action == "ADJUST_GRID":
        return {
            "tipo":   "ignorar",
            "motivo": "ADJUST_GRID via webhook no soportado — usar JSONL poller",
            "symbol": symbol,
        }

    raise ValueError(f"action BOT_GRID desconocida: {action}")
