"""
Estrategia QLEARNING - Worker Q-Learning.

Estado: regime | volatility | momentum  (3x3x3 = 27 estados)
Reutiliza core/state_encoder.py (sin cambios).

Payload esperado de TradingView (mismo formato actual):
{
  "status": "pending",
  "signal": {
    "symbol": "SOLUSD",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.1,
    "params": {
      "price":      150.0,
      "sl":         148.0,
      "tp":         154.0,
      "atr":        1.5,
      "regime":     "trend_up",
      "volatility": "mid",
      "momentum":   "bullish"
    }
  }
}

Nota: /webhook/tv sigue apuntando a este worker via la ruta legacy.
      /webhook/strategy/qlearning es la nueva ruta equivalente.
"""
from core.strategy_worker import StrategyWorker
from core.state_encoder   import encode_state as core_encode_state


class QLearningWorker(StrategyWorker):
    strategy_id = "qlearning"

    def encode_state(self, params: dict) -> str:
        """Delegates to core/state_encoder.py: regime|volatility|momentum."""
        return core_encode_state(params)
