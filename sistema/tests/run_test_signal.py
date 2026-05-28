"""
run_test_signal.py - Ejecuta el pipeline completo en modo DRY_RUN.

Patron identico a bot2/run_analysis.py:
  - Ignora si bot1 esta disponible o no
  - Siempre usa DRY_RUN=True
  - Imprime el resultado completo del pipeline Q-Learning

USO:
    python run_test_signal.py
    python run_test_signal.py --regime trend_down --momentum bearish
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_test_signal")

os.environ["DRY_RUN"] = "true"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config
from core.qlearning_agent        import QLearningAgent
from core.tv_signal_parser       import parse_tv_envelope
from manager.qlearning_trainer   import QLearningTrainer
from sender                      import signal_formatter
from strategies.strategy_tv_qlearning import TVQLearningStrategy


def run(regime="trend_up", volatility="mid", momentum="bullish",
        symbol="SPY", action="buy", price=520.0, sl=517.0, tp=527.0, atr=1.5, size=0.1):

    envelope_data = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "status":     "pending",
        "processed":  False,
        "source":     "tradingview_test",
        "signal": {
            "strategy_id": "strategy_tv_qlearning",
            "symbol":      symbol,
            "action":      action,
            "confidence":  0.75,
            "size":        size,
            "params": {
                "price":      price,
                "sl":         sl,
                "tp":         tp,
                "atr":        atr,
                "regime":     regime,
                "volatility": volatility,
                "momentum":   momentum,
            },
        },
    }

    print("\n" + "=" * 60)
    print("  Bot3 Q-Learning - Test Signal (DRY RUN)")
    print("=" * 60)
    print(f"\nInput:")
    print(f"  Symbol    : {symbol}")
    print(f"  Action    : {action}")
    print(f"  Regime    : {regime}")
    print(f"  Volatility: {volatility}")
    print(f"  Momentum  : {momentum}")
    print(f"  Price     : {price} | SL: {sl} | TP: {tp} | ATR: {atr}")

    envelope = parse_tv_envelope(envelope_data)
    agent    = QLearningAgent()
    strategy = TVQLearningStrategy(agent)
    decision = strategy.decide(envelope)

    print(f"\nQ-Learning Decision:")
    print(f"  State    : {decision['state']}")
    print(f"  Q-Values : {agent.get_q_values(decision['state'])}")
    print(f"  Action   : {decision['ql_action']}")
    print(f"  Q-Value  : {decision['q_value']:.6f}")
    print(f"  Execute  : {decision['execute']}")
    print(f"  Side     : {decision['side']}")
    print(f"  Size mult: {decision['size_multiplier']}")
    print(f"  Reason   : {decision['reason']}")
    print(f"  Epsilon  : {agent.epsilon:.4f}")
    print(f"  Alpha    : {agent.alpha:.4f}")

    if decision["execute"]:
        final_size = round(size * decision["size_multiplier"], 4)
        payload = signal_formatter.build_payload(
            symbol     = symbol,
            action     = decision["side"],
            confidence = 0.75,
            size       = final_size,
            ql_action  = decision["ql_action"],
            ql_state   = decision["state"],
            q_value    = decision["q_value"],
            regime     = regime,
            volatility = volatility,
            momentum   = momentum,
            price      = price,
            sl         = sl,
            tp         = tp,
            atr        = atr,
        )
        print(f"\nPayload que se enviaria a bot1 ({config.WEBHOOK_URL}):")
        print(json.dumps(payload, indent=2))
    else:
        print(f"\nQ-Learning DESCARTARIA esta senal ({decision['ql_action']})")

    print("\n" + "=" * 60)
    print("  [DRY RUN] No se envio nada a bot1")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test signal Q-Learning (dry run)")
    parser.add_argument("--symbol",     default="SPY")
    parser.add_argument("--action",     default="buy",      choices=["buy", "sell"])
    parser.add_argument("--regime",     default="trend_up", choices=["trend_up", "trend_down", "range"])
    parser.add_argument("--volatility", default="mid",      choices=["low", "mid", "high"])
    parser.add_argument("--momentum",   default="bullish",  choices=["bullish", "bearish", "neutral"])
    parser.add_argument("--price",      default=520.0,  type=float)
    parser.add_argument("--sl",         default=517.0,  type=float)
    parser.add_argument("--tp",         default=527.0,  type=float)
    parser.add_argument("--atr",        default=1.5,    type=float)
    parser.add_argument("--size",       default=0.1,    type=float)
    args = parser.parse_args()
    run(**vars(args))
