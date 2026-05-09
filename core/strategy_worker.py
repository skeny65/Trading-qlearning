"""
strategy_worker.py - Clase base para todos los workers de estrategia.

Cada estrategia (Apuesta, QLearning, Tanque) hereda StrategyWorker y solo
necesita implementar encode_state(params) con su logica especifica.

El resto del pipeline (Q-Learning, decide, logging) es compartido y reutilizable.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from core.qlearning_agent import QLearningAgent
from manager.qlearning_trainer import QLearningTrainer

logger = logging.getLogger("bot3.strategy_worker")

ACTIONS = ["EXECUTE_FULL", "EXECUTE_HALF", "SKIP", "INVERT"]


class StrategyWorker(ABC):
    """
    Base class for all strategy workers.

    Subclasses must define:
        strategy_id (str)  -- unique identifier, e.g. "apuesta"
        encode_state(params: dict) -> str  -- strategy-specific state encoding
    """

    strategy_id: str  # override in subclass

    def __init__(self):
        data_dir = f"data/strategies/{self.strategy_id}"
        self.agent   = QLearningAgent(data_dir=data_dir)
        self.trainer = QLearningTrainer(self.agent, data_dir=data_dir)
        logger.info(
            f"[{self.strategy_id}] Worker inicializado | "
            f"eps={self.agent.epsilon:.4f} alpha={self.agent.alpha:.4f}"
        )

    @abstractmethod
    def encode_state(self, params: dict) -> str:
        """Convert signal params dict into a discrete state string."""

    # -------------------------------------------------------------------------
    # Signal parsing (shared; can be overridden if the envelope differs)
    # -------------------------------------------------------------------------

    def parse_signal(self, body: dict) -> dict:
        """
        Extract common fields from a TradingView webhook body.
        Returns: {symbol, action, confidence, size, params}
        """
        signal = body.get("signal", {})
        return {
            "symbol":     str(signal.get("symbol", "UNKNOWN")).upper(),
            "action":     str(signal.get("action", "buy")).lower(),
            "confidence": float(signal.get("confidence", 0.75)),
            "size":       float(signal.get("size", 0.1)),
            "params":     signal.get("params", {}),
        }

    # -------------------------------------------------------------------------
    # Decision (shared — uses encode_state which each strategy overrides)
    # -------------------------------------------------------------------------

    def decide(self, body: dict) -> dict:
        """
        Full decision pipeline: parse -> encode state -> Q-Learning -> decision dict.

        Returns:
            symbol, original_action, ql_action, state, execute, side,
            size, size_multiplier, confidence, q_value, strategy_id, reason
        """
        parsed = self.parse_signal(body)
        symbol         = parsed["symbol"]
        original_side  = parsed["action"]
        confidence     = parsed["confidence"]
        raw_size       = parsed["size"]
        params         = parsed["params"]

        state    = self.encode_state(params)
        action   = self.agent.choose_action(state)
        q_values = self.agent.get_q_values(state)
        q_value  = q_values.get(action, 0.0)

        logger.info(
            f"[{self.strategy_id}] {symbol} signal={original_side} | "
            f"state={state} | ql_action={action} | q={q_value:.4f}"
        )

        if action == "EXECUTE_FULL":
            side, multiplier, execute = original_side, 1.0, True
        elif action == "EXECUTE_HALF":
            side, multiplier, execute = original_side, 0.5, True
        elif action == "SKIP":
            side, multiplier, execute = original_side, 0.0, False
        elif action == "INVERT":
            side      = "sell" if original_side == "buy" else "buy"
            multiplier, execute = 0.5, True
        else:
            side, multiplier, execute = original_side, 0.0, False

        reason = self._action_reason(action, original_side, side)

        return {
            "symbol":          symbol,
            "original_action": original_side,
            "ql_action":       action,
            "state":           state,
            "execute":         execute,
            "side":            side,
            "size":            round(raw_size * multiplier, 4),
            "size_multiplier": multiplier,
            "confidence":      confidence,
            "q_value":         q_value,
            "strategy_id":     self.strategy_id,
            "reason":          reason,
            "params":          params,
        }

    def _action_reason(self, action: str, original: str, final: str) -> str:
        reasons = {
            "EXECUTE_FULL": f"[{self.strategy_id}] Q-Learning: execute full",
            "EXECUTE_HALF": f"[{self.strategy_id}] Q-Learning: execute half",
            "SKIP":         f"[{self.strategy_id}] Q-Learning: skip signal",
            "INVERT":       f"[{self.strategy_id}] Q-Learning: invert {original}->{final}",
        }
        return reasons.get(action, f"[{self.strategy_id}] unknown action: {action}")

    # -------------------------------------------------------------------------
    # Q-Learning update (hindsight learning)
    # -------------------------------------------------------------------------

    def update_q(
        self,
        state:      str,
        action:     str,
        reward:     float,
        next_state: str,
    ) -> float:
        """Update Q-table and decay params. Returns new Q value."""
        new_q = self.agent.update(state, action, reward, next_state)
        self.agent.decay_params()
        self.agent.record_reward(reward)
        self.trainer.append_experience(state, action, reward, next_state)
        self.trainer.save_and_backup()
        logger.info(
            f"[{self.strategy_id}] Q-update: {state} -> {action} "
            f"reward={reward:.4f} new_q={new_q:.6f}"
        )
        return new_q

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        return {
            "strategy_id":   self.strategy_id,
            "paused":        self.agent.paused,
            "epsilon":       round(self.agent.epsilon, 6),
            "alpha":         round(self.agent.alpha,   6),
            "qtable_states": len(self.agent.q_table),
        }
