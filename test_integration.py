"""
test_integration.py - Prueba de integracion end-to-end con bot1.

Identico al patron de bot2/test_integration.py:
  Envia un webhook REAL a bot1 (DRY_RUN=False forzado) y verifica la respuesta.

USO:
    python test_integration.py

PASOS:
  1. Parsea un envelope TradingView de ejemplo
  2. Aplica Q-Learning (decision de agente)
  3. Envia a bot1 via webhook_client (DRY_RUN=False forzado)
  4. Muestra respuesta de bot1
  5. Escribe fila en logs/trade_log.xlsx
  6. Append en state/decision_log.jsonl
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Asegurar raiz en path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_integration")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Forzar DRY_RUN=False para test real
os.environ["DRY_RUN"] = "false"

import config
from core.qlearning_agent        import QLearningAgent
from core.tv_signal_parser       import parse_tv_envelope
from excel_logger                import append_excel_rows
from manager.qlearning_trainer   import QLearningTrainer
from sender                      import webhook_client, signal_formatter
from strategies.strategy_tv_qlearning import TVQLearningStrategy

# Envelope de prueba (mismo formato que TradingView)
TEST_ENVELOPE = {
    "timestamp":  datetime.now(timezone.utc).isoformat(),
    "status":     "pending",
    "processed":  False,
    "source":     "tradingview",
    "signal": {
        "strategy_id": "strategy_tv_qlearning",
        "symbol":      "SPY",
        "action":      "buy",
        "confidence":  0.75,
        "size":        0.1,
        "params": {
            "price":      520.50,
            "sl":         518.00,
            "tp":         525.50,
            "atr":        1.50,
            "regime":     "trend_up",
            "volatility": "mid",
            "momentum":   "bullish",
        },
    },
}


def run_integration_test():
    logger.info("=" * 60)
    logger.info("  Bot3 Q-Learning - Test de Integracion")
    logger.info(f"  Webhook URL: {config.WEBHOOK_URL}")
    logger.info("=" * 60)

    # Paso 1: Parsear envelope
    logger.info("\nPaso 1: Parsear envelope TradingView...")
    envelope = parse_tv_envelope(TEST_ENVELOPE)
    logger.info(f"  symbol={envelope.signal.symbol} action={envelope.signal.action} "
                f"regime={envelope.signal.params.regime}")

    # Paso 2: Q-Learning decision
    logger.info("\nPaso 2: Decision Q-Learning...")
    agent    = QLearningAgent()
    trainer  = QLearningTrainer(agent)
    strategy = TVQLearningStrategy(agent)
    decision = strategy.decide(envelope)
    logger.info(f"  ql_action={decision['ql_action']} state={decision['state']} "
                f"q_value={decision['q_value']:.4f} execute={decision['execute']}")

    if not decision["execute"]:
        logger.info(f"  Q-Learning descarto la senal: {decision['reason']}")
        return

    # Paso 3: Construir payload y enviar a bot1
    params   = envelope.signal.params
    signal   = envelope.signal
    payload  = signal_formatter.build_payload(
        symbol     = signal.symbol,
        action     = decision["side"],
        confidence = signal.confidence,
        size       = round(signal.size * decision["size_multiplier"], 4),
        ql_action  = decision["ql_action"],
        ql_state   = decision["state"],
        q_value    = decision["q_value"],
        regime     = params.regime,
        volatility = params.volatility,
        momentum   = params.momentum,
        price      = params.price,
        sl         = params.sl,
        tp         = params.tp,
        atr        = params.atr,
    )

    logger.info(f"\nPaso 3: Enviando a bot1...")
    logger.info(f"  URL: {config.WEBHOOK_URL}")
    logger.info(f"  Payload: {json.dumps(payload, indent=2)}")

    response = webhook_client.send(payload)
    logger.info(f"\nRespuesta de bot1: {response}")

    # Paso 4: Excel
    logger.info("\nPaso 4: Registrando en Excel...")
    row = {
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "event_id":       "integration_test",
        "mode":           "INTEGRATION_TEST",
        "symbol":         signal.symbol,
        "tv_action":      signal.action,
        "ql_action":      decision["ql_action"],
        "ql_state":       decision["state"],
        "q_value":        decision["q_value"],
        "regime":         params.regime,
        "volatility":     params.volatility,
        "momentum":       params.momentum,
        "price":          params.price,
        "execute":        True,
        "webhook_status": response.get("status", "unknown"),
        "order_id":       response.get("order_id", ""),
        "reason":         decision["reason"],
    }
    append_excel_rows([row])
    logger.info("  OK")

    # Paso 5: decision_log
    logger.info("\nPaso 5: Registrando en decision_log.jsonl...")
    log_path = Path("state") / "decision_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "source": "integration_test"}) + "\n")
    logger.info("  OK")

    logger.info("\n" + "=" * 60)
    logger.info("  Test de integracion completado")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_integration_test()
