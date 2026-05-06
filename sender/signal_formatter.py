"""
signal_formatter.py - Construye payloads compatibles con bot1 (patron bot2).

strategy_id : "bot3_qlearning"
source      : "bot3_qlearning_agent"
endpoint    : POST /webhook/bot3
"""
from datetime import datetime, timezone


STRATEGY_ID = "bot3_qlearning"
SOURCE      = "bot3_qlearning_agent"


def build_payload(
    symbol:          str,
    action:          str,
    confidence:      float,
    size:            float,
    ql_action:       str,
    ql_state:        str,
    q_value:         float,
    regime:          str,
    volatility:      str,
    momentum:        str,
    price:           float = 0.0,
    sl:              float = 0.0,
    tp:              float = 0.0,
    atr:             float = 0.0,
) -> dict:
    """
    Construye el payload para bot1.

    Identico al patron de bot2.build_spy_payload() pero para Q-Learning:
    {
      "timestamp": "...",
      "status": "pending",
      "signal": {
        "strategy_id": "bot3_qlearning",
        "symbol": "SPY",
        "action": "buy",
        "confidence": 0.75,
        "size": 0.1,
        "params": { ... }
      }
    }
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status":    "pending",
        "signal": {
            "strategy_id": STRATEGY_ID,
            "symbol":      symbol,
            "action":      action,
            "confidence":  round(confidence, 4),
            "size":        round(size, 4),
            "params": {
                "source":     SOURCE,
                "ql_action":  ql_action,
                "ql_state":   ql_state,
                "q_value":    round(q_value, 6),
                "regime":     regime,
                "volatility": volatility,
                "momentum":   momentum,
                "price":      price,
                "sl":         sl,
                "tp":         tp,
                "atr":        atr,
            },
        },
    }


def build_no_signal_payload(symbol: str, reason: str) -> dict:
    """Payload informativo para ciclos sin senal (identico al patron bot2)."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status":    "no_signal",
        "signal": {
            "strategy_id": STRATEGY_ID,
            "symbol":      symbol,
            "action":      "none",
            "confidence":  0.0,
            "size":        0.0,
            "params":      {"source": SOURCE, "reason": reason},
        },
    }
