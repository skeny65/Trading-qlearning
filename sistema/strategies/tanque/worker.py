"""
Estrategia 3 (TANQUE) - Worker Q-Learning.

Estado: entry_strength | bar_zone | pattern  (3x3x3 = 27 estados)
    entry_strength : strong | moderate | weak
    bar_zone       : recent (<=3 bars) | mid (<=10 bars) | old (>10 bars)
    pattern        : inside_bar | breakout | pullback

Flujo de 2 alertas por operacion:
    Alerta 1 (signal_type: "open")  -> Q-Learning decide si ejecutar
    Alerta 2 (signal_type: "close") -> cierre inmediato + update Q

Payload apertura (TradingView):
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "confidence":  0.75,
    "size":        0.1,
    "params": {
      "price":          150.0,
      "entry_strength": "strong",
      "bar_count":      2,
      "pattern":        "inside_bar"
    }
  }
}

Payload cierre (TradingView):
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        152.0,
      "entry_price":  150.0,
      "close_reason": "cross",
      "pnl_pct":      1.33
    }
  }
}

NOTA: encode_state() usa los datos del payload de apertura.
      Ajustar cuando se defina el payload definitivo del Pine de Tanque.
"""
from core.strategy_worker import StrategyWorker


class TanqueWorker(StrategyWorker):
    strategy_id = "3"

    def encode_state(self, params: dict) -> str:
        """
        Scaffold: entry_strength|bar_zone|pattern
        Ajustar cuando se conozca el payload real del Pine de Tanque.
        """
        # entry_strength
        strength_raw = str(params.get("entry_strength", "moderate")).lower()
        if strength_raw in ("strong", "high", "3"):
            entry_strength = "strong"
        elif strength_raw in ("weak", "low", "1"):
            entry_strength = "weak"
        else:
            entry_strength = "moderate"

        # bar_zone (cuantos bars desde el setup)
        bar_count = int(params.get("bar_count", 5))
        if bar_count <= 3:
            bar_zone = "recent"
        elif bar_count <= 10:
            bar_zone = "mid"
        else:
            bar_zone = "old"

        # pattern
        pattern_raw = str(params.get("pattern", "pullback")).lower()
        if "inside" in pattern_raw:
            pattern = "inside_bar"
        elif "break" in pattern_raw:
            pattern = "breakout"
        else:
            pattern = "pullback"

        return f"{entry_strength}|{bar_zone}|{pattern}"
