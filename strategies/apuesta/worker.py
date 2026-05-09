"""
Estrategia APUESTA - Worker Q-Learning.

Estado: price_zone | rr_level | hour_zone  (3x3x3 = 27 estados)
    price_zone : high (>100) | mid (>50) | low (<=50)
    rr_level   : excellent (>=1.5) | good (>=1.0) | poor (<1.0)
    hour_zone  : us_hours (13-17 UTC) | asia_hours (0-2 / 8-9 UTC) | eu_hours (resto)

Historico real: 183 trades, WR 54.9%, PF 1.22
Filtros Pine: VWAP, ADX min 16, volumen, ATR
R:R optimo: 1:1.5

Payload esperado de TradingView:
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSD",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.1,
    "params": {
      "price": 150.0,
      "sl":    148.0,
      "tp":    154.0,
      "rr":    1.5,
      "atr":   1.0
    }
  }
}
"""
from datetime import datetime, timezone
from core.strategy_worker import StrategyWorker


class ApuestaWorker(StrategyWorker):
    strategy_id = "apuesta"

    def encode_state(self, params: dict) -> str:
        """
        Builds state: "{price_zone}|{rr_level}|{hour_zone}"
        Falls back gracefully if fields are missing.
        """
        price = float(params.get("price", 0.0))
        sl    = float(params.get("sl",    0.0))
        tp    = float(params.get("tp",    0.0))
        rr    = float(params.get("rr",    0.0))

        # Compute RR from sl/tp if rr not explicit
        if rr == 0.0 and sl != 0.0 and tp != 0.0 and price != 0.0:
            risk   = abs(price - sl)
            reward = abs(tp - price)
            rr     = round(reward / risk, 2) if risk > 0 else 0.0

        # price_zone
        if price > 100:
            price_zone = "high"
        elif price > 50:
            price_zone = "mid"
        else:
            price_zone = "low"

        # rr_level
        if rr >= 1.5:
            rr_level = "excellent"
        elif rr >= 1.0:
            rr_level = "good"
        else:
            rr_level = "poor"

        # hour_zone (UTC)
        hour = datetime.now(timezone.utc).hour
        if hour in (13, 14, 15, 16, 17):
            hour_zone = "us_hours"
        elif hour in (0, 1, 2, 8, 9):
            hour_zone = "asia_hours"
        else:
            hour_zone = "eu_hours"

        return f"{price_zone}|{rr_level}|{hour_zone}"
