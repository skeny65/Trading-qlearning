"""
adapter_generico.py - Adaptador base para emisores con formato minimo documentado.

Formato esperado (documentado):
{
  "tipo": "open" | "close",
  "symbol": "SOLUSDT",
  "side": "buy" | "sell",
  "price": 85.30,
  "sl": 85.17,     # opcional
  "tp": 86.50,     # opcional
  "entry_price": 85.30,   # solo en close
  "pnl_pct": 0.29,        # solo en close (opcional)
  "close_reason": "texto" # solo en close (opcional)
}
"""
from __future__ import annotations


def parse(body: dict, folder_id: str) -> dict:
    """Parsea formato generico minimo."""
    tipo   = str(body.get("tipo", "open")).lower()
    symbol = str(body.get("symbol", "")).upper()
    side   = str(body.get("side",   "buy")).lower()

    if not symbol:
        raise ValueError("Campo 'symbol' ausente en el payload")
    if side not in ("buy", "sell"):
        raise ValueError(f"Campo 'side' invalido: {side}")
    if tipo not in ("open", "close"):
        raise ValueError(f"Campo 'tipo' invalido: {tipo}")

    return {
        "id_carpeta":   folder_id,
        "tipo":         tipo,
        "symbol":       symbol,
        "side":         side,
        "price":        float(body.get("price",       0.0)),
        "sl":           float(body.get("sl",          0.0)) or None,
        "tp":           float(body.get("tp",          0.0)) or None,
        "entry_price":  float(body.get("entry_price", 0.0)) or None,
        "pnl_pct":      float(body.get("pnl_pct",     0.0)) or None,
        "close_reason": str(body.get("close_reason",  "señal_close")) if tipo == "close" else None,
        "raw":          body,
    }
