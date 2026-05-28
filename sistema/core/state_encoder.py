"""
Maps TradingView signal params to a discrete Q-Learning state string.

State space: regime x volatility x momentum  (3x3x3 = 27 states)
Key format : "trend_up|mid|bullish"
"""
from typing import Optional

REGIMES     = {"trend_up", "trend_down", "range"}
VOLATILITIES = {"low", "mid", "high"}
MOMENTUMS   = {"bullish", "bearish", "neutral"}

_DEF_REGIME = "range"
_DEF_VOL    = "mid"
_DEF_MOM    = "neutral"


def encode_state(params: dict) -> str:
    """
    Encode market params dict into state key "regime|volatility|momentum".

    Raises:
        ValueError: if any required field is None.
    """
    regime     = params.get("regime")
    volatility = params.get("volatility")
    momentum   = params.get("momentum")

    if regime is None or volatility is None or momentum is None:
        raise ValueError(
            f"State params must not be None: "
            f"regime={regime}, volatility={volatility}, momentum={momentum}"
        )

    if regime not in REGIMES:
        regime = _DEF_REGIME
    if volatility not in VOLATILITIES:
        volatility = _DEF_VOL
    if momentum not in MOMENTUMS:
        momentum = _DEF_MOM

    return f"{regime}|{volatility}|{momentum}"


def decode_state(state: str) -> dict:
    """Decode a state string back to its component dict."""
    parts = state.split("|")
    if len(parts) != 3:
        return {"regime": _DEF_REGIME, "volatility": _DEF_VOL, "momentum": _DEF_MOM}
    return {"regime": parts[0], "volatility": parts[1], "momentum": parts[2]}


def all_states() -> list:
    """Return all 27 possible state strings (sorted)."""
    return [
        f"{r}|{v}|{m}"
        for r in sorted(REGIMES)
        for v in sorted(VOLATILITIES)
        for m in sorted(MOMENTUMS)
    ]
