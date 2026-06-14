"""
adapter_tradingview.py - Convierte el payload de TradingView al formato interno SignalInterna.

Formato esperado de TradingView:
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "buy" | "sell" | "close_buy" | "close_sell",
    "signal_type": "open" | "close",
    "size": 0.1,
    "params": {
      "price": 85.30,
      "sl": 85.17,
      "tp": 86.50,
      "entry_price": 85.30,   # solo en close
      "pnl_pct": 0.29,        # solo en close (opcional)
      "close_reason": "Cruce contrario",  # solo en close
      ...campos extra ignorados...
    }
  }
}
"""
from __future__ import annotations
from typing import Optional


def parse(body: dict, folder_id: str) -> dict:
    """
    Parsea un payload TradingView y retorna un SignalInterna.
    Lanza ValueError si el payload es invalido o el symbol no esta permitido.
    """
    if body.get("status") != "pending":
        return {
            "id_carpeta": folder_id,
            "tipo":       "ignorar",
            "raw":        body,
            "motivo":     f"status={body.get('status')} — sin accion",
        }

    signal = body.get("signal", {})
    if not signal:
        raise ValueError("Campo 'signal' ausente en el payload")

    symbol      = str(signal.get("symbol", "")).upper()
    action      = str(signal.get("action", "")).lower()
    signal_type = str(signal.get("signal_type", "open")).lower()
    params      = signal.get("params", {})

    if not symbol:
        raise ValueError("Campo signal.symbol ausente")

    # Determinar lado (buy/sell) a partir de action
    if "sell" in action or "short" in action:
        side = "sell"
    else:
        side = "buy"

    if signal_type == "close":
        return {
            "id_carpeta":   folder_id,
            "tipo":         "close",
            "symbol":       symbol,
            "side":         side,
            "price":        float(params.get("price",       0.0)),
            "sl":           None,
            "tp":           None,
            "entry_price":  float(params.get("entry_price", 0.0)) or None,
            "pnl_pct":      float(params.get("pnl_pct",     0.0)) or None,
            "close_reason": str(params.get("close_reason",  "señal_close")),
            "raw":          body,
        }

    # open
    sl_distance_raw = params.get("sl_distance")
    risk_pct_raw    = params.get("risk_pct")
    return {
        "id_carpeta":   folder_id,
        "tipo":         "open",
        "symbol":       symbol,
        "side":         side,
        "price":        float(params.get("price", 0.0)),
        "sl":           float(params.get("sl",    0.0)) or None,
        "tp":           float(params.get("tp",    0.0)) or None,
        "sl_distance":  float(sl_distance_raw) if sl_distance_raw is not None else None,
        "risk_pct":     float(risk_pct_raw)    if risk_pct_raw    is not None else None,
        "entry_price":  None,
        "pnl_pct":      None,
        "close_reason": None,
        "raw":          body,
    }
