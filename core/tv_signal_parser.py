"""
Parser for TradingView webhook envelopes.

Envelope format (body):
    {
        "timestamp": "2026-05-03T14:30:00Z",
        "status": "pending",
        "processed": false,
        "source": "tradingview",
        "signal": {
            "strategy_id": "strategy_tv_qlearning",
            "symbol": "SPY",
            "action": "buy",
            "confidence": 0.75,
            "size": 0.1,
            "params": {
                "price": 512.30,
                "sl": 510.20,
                "tp": 516.50,
                "atr": 1.45,
                "regime": "trend_up",
                "volatility": "mid",
                "momentum": "bullish"
            }
        }
    }

Secret is validated via the X-Webhook-Secret header in bot.py.
"""
from typing import Optional

from pydantic import BaseModel, validator
import logging

logger = logging.getLogger("bot3.tv_parser")

_VALID_REGIMES     = {"trend_up", "trend_down", "range"}
_VALID_VOLATILITIES = {"low", "mid", "high"}
_VALID_MOMENTUMS   = {"bullish", "bearish", "neutral"}
_VALID_ACTIONS     = {"buy", "sell"}


class TVParams(BaseModel):
    price:      float
    sl:         float
    tp:         float
    atr:        float
    regime:     str
    volatility: str
    momentum:   str

    @validator("regime")
    def _regime(cls, v):
        if v not in _VALID_REGIMES:
            raise ValueError(f"regime must be one of {_VALID_REGIMES}, got '{v}'")
        return v

    @validator("volatility")
    def _volatility(cls, v):
        if v not in _VALID_VOLATILITIES:
            raise ValueError(f"volatility must be one of {_VALID_VOLATILITIES}, got '{v}'")
        return v

    @validator("momentum")
    def _momentum(cls, v):
        if v not in _VALID_MOMENTUMS:
            raise ValueError(f"momentum must be one of {_VALID_MOMENTUMS}, got '{v}'")
        return v


class TVSignalInner(BaseModel):
    strategy_id: str   = "strategy_tv_qlearning"
    symbol:      str
    action:      str
    confidence:  float = 0.75
    size:        float = 0.1
    params:      TVParams

    @validator("action")
    def _action(cls, v):
        v = v.lower()
        if v not in _VALID_ACTIONS:
            raise ValueError(f"action must be buy or sell, got '{v}'")
        return v


class TVEnvelope(BaseModel):
    timestamp: Optional[str] = None
    status:    str            = "pending"
    processed: bool           = False
    source:    str            = "tradingview"
    signal:    TVSignalInner


def parse_tv_envelope(body: dict) -> TVEnvelope:
    """Parse and validate a TradingView webhook body dict."""
    return TVEnvelope(**body)
