"""
Estrategia 4 - Worker Q-Learning (scaffold generico).

Estado: price_zone | rr_level | hour_zone  (3x3x3 = 27 estados)
Ajustar encode_state() cuando definas la logica especifica de esta estrategia.

Payload minimo esperado de TradingView:
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSDT",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.1,
    "params": { "price": 93.73, "sl": 93.63, "tp": 93.93 }
  }
}
"""
from datetime import datetime, timezone
from core.strategy_worker import StrategyWorker


class Strategy4Worker(StrategyWorker):
    strategy_id = "4"

    def encode_state(self, params: dict) -> str:
        price = float(params.get("price", 0.0))
        sl    = float(params.get("sl",    0.0))
        tp    = float(params.get("tp",    0.0))

        risk   = abs(price - sl)
        reward = abs(tp - price)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        price_zone = "high" if price > 100 else ("mid" if price > 50 else "low")
        rr_level   = "excellent" if rr >= 1.5 else ("good" if rr >= 1.0 else "poor")

        hour = datetime.now(timezone.utc).hour
        if hour in (13, 14, 15, 16, 17):
            hour_zone = "us"
        elif hour in (0, 1, 2, 8, 9):
            hour_zone = "asia"
        else:
            hour_zone = "eu"

        return f"{price_zone}|{rr_level}|{hour_zone}"
