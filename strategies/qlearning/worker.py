"""
Estrategia 2 (QLEARNING) - Worker Q-Learning.

Estado 5D: regime | momentum | setup_type | htf_bias | trend_strength
           3      x 3        x 3          x 3        x 3  = 243 estados

Permite al agente distinguir, por ejemplo:
  "trend_up|bullish|breakout|bull|extreme"  → EXECUTE_FULL aprendido
  "trend_up|bullish|breakout|bear|weak"     → SKIP aprendido (contra-tendencia HTF)

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
    "confidence":  0.7,
    "size":        0.1,
    "params": {
      "price":          93.73,
      "sl":             93.63,
      "tp":             93.93,
      "atr":            0.066,
      "adx":            40.66,
      "rsi":            68.66,
      "regime":         "trend_up",
      "momentum":       "bullish",
      "setup_type":     "breakout",
      "htf_bias":       "bull",
      "trend_strength": "extreme"
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
      "price":        94.20,
      "entry_price":  93.73,
      "close_reason": "cross",
      "pnl_pct":      0.50
    }
  }
}
"""
from core.strategy_worker import StrategyWorker

# Valores validos por dimension (fallback al primero si llega algo inesperado)
_REGIMES         = {"trend_up", "trend_down", "range"}
_MOMENTUMS       = {"bullish", "bearish", "neutral"}
_SETUP_TYPES     = {"breakout", "pullback", "trend"}
_HTF_BIASES      = {"bull", "bear", "neutral"}
_TREND_STRENGTHS = {"extreme", "strong", "weak"}


def _norm(value: str, valid: set, default: str) -> str:
    v = str(value).lower().strip()
    return v if v in valid else default


class QLearningWorker(StrategyWorker):
    strategy_id = "2"

    def encode_state(self, params: dict) -> str:
        """
        Estado 5D: regime|momentum|setup_type|htf_bias|trend_strength
        243 combinaciones posibles.
        """
        regime   = _norm(params.get("regime",         "range"),   _REGIMES,         "range")
        momentum = _norm(params.get("momentum",        "neutral"), _MOMENTUMS,       "neutral")

        # setup_type: acepta breakout/pullback/trend
        raw_setup = str(params.get("setup_type", "trend")).lower()
        if "break" in raw_setup:
            setup_type = "breakout"
        elif "pull" in raw_setup or "retrace" in raw_setup:
            setup_type = "pullback"
        else:
            setup_type = "trend"

        # htf_bias: bull/bear/neutral
        raw_htf = str(params.get("htf_bias", "neutral")).lower()
        if raw_htf in ("bull", "bullish"):
            htf_bias = "bull"
        elif raw_htf in ("bear", "bearish"):
            htf_bias = "bear"
        else:
            htf_bias = "neutral"

        # trend_strength: extreme/strong/weak  (desde campo o desde ADX)
        raw_strength = str(params.get("trend_strength", "")).lower()
        if raw_strength in ("extreme",):
            trend_strength = "extreme"
        elif raw_strength in ("strong", "high"):
            trend_strength = "strong"
        elif raw_strength in ("moderate", "mid", "medium"):
            trend_strength = "strong"   # moderado → strong (simplificar a 3 niveles)
        elif raw_strength in ("weak", "low"):
            trend_strength = "weak"
        else:
            # fallback: derivar de ADX si viene en params
            adx = float(params.get("adx", 0.0))
            if adx >= 40:
                trend_strength = "extreme"
            elif adx >= 20:
                trend_strength = "strong"
            else:
                trend_strength = "weak"

        return f"{regime}|{momentum}|{setup_type}|{htf_bias}|{trend_strength}"
