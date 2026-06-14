"""
adapter_bot_manager.py - Adaptador para señales BOT_MANAGER v2.0 (carpeta 10).

Protocolo unificado compartido con BOT_GRID. Usa source="bot_manager".
Acciones via HTTP POST /signal:
  OPEN   → tipo=open
  CLOSE  → tipo=close  (position_id requerido)
  ADJUST → tipo=adjust (position_id requerido, mueve SL/TP)
  PAUSE  → tipo=control
  RESUME → tipo=control

El webhook /webhook/10 sigue aceptando formato generico simple como fallback.
"""

_VALID_ACTIONS = {"OPEN", "CLOSE", "ADJUST", "PAUSE", "RESUME"}


def parse(body: dict, folder_id: str) -> dict:
    if body.get("action", "").upper() in _VALID_ACTIONS:
        return _parse_v2(body)
    from core.adapters.adapter_generico import parse as _parse_generico
    return _parse_generico(body, folder_id)


def _parse_v2(body: dict) -> dict:
    action = body.get("action", "").upper()
    symbol = str(body.get("symbol", "")).upper()

    if not symbol:
        raise ValueError("Campo 'symbol' requerido")

    if action == "OPEN":
        if not body.get("side"):
            raise ValueError("OPEN requiere campo 'side'")
        if body.get("sl") is None:
            raise ValueError("OPEN requiere campo 'sl'")
        return {
            "tipo":              "open",
            "symbol":            symbol,
            "side":              str(body["side"]).lower(),
            "price":             float(body.get("price", 0)),
            "sl":                float(body["sl"]),
            "tp":                float(body["tp"]) if body.get("tp") is not None else None,
            "position_id":       body.get("position_id"),
            "size_usdt":         body.get("size_usdt"),
            "size_pct":          body.get("size_pct"),
            "trailing_callback": body.get("trailing_callback"),
            "signal_id":         body.get("signal_id", ""),
            "source":            body.get("source", "bot_manager"),
            "strategy":          body.get("strategy", ""),
            "confidence":        body.get("confidence"),
        }

    if action == "CLOSE":
        return {
            "tipo":         "close",
            "symbol":       symbol,
            "price":        float(body.get("price", 0)),
            "close_reason": "CLOSE_BOT_MANAGER",
            "position_id":  body.get("position_id"),
            "signal_id":    body.get("signal_id", ""),
            "source":       body.get("source", "bot_manager"),
        }

    if action == "ADJUST":
        if not body.get("position_id"):
            raise ValueError("ADJUST requiere campo 'position_id'")
        return {
            "tipo":              "adjust",
            "symbol":            symbol,
            "position_id":       body["position_id"],
            "sl":                float(body["sl"]) if body.get("sl") is not None else None,
            "tp":                float(body["tp"]) if body.get("tp") is not None else None,
            "trailing_callback": body.get("trailing_callback"),
            "signal_id":         body.get("signal_id", ""),
            "source":            body.get("source", "bot_manager"),
        }

    # PAUSE / RESUME
    return {
        "tipo":      "control",
        "control":   action,
        "symbol":    symbol,
        "signal_id": body.get("signal_id", ""),
        "source":    body.get("source", "bot_manager"),
    }
