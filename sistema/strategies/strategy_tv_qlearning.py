"""
Strategy: TradingView Q-Learning.

Maps a validated TVEnvelope through the Q-Learning agent to produce
an execution decision (EXECUTE_FULL / EXECUTE_HALF / SKIP / INVERT).
"""
import logging
from core.state_encoder  import encode_state
from core.qlearning_agent import QLearningAgent
from core.tv_signal_parser import TVEnvelope

logger = logging.getLogger("bot3.strategy_tv_qlearning")

STRATEGY_ID = "strategy_tv_qlearning"


class TVQLearningStrategy:
    """Wraps the Q-Learning agent with the strategy interface."""

    strategy_id = STRATEGY_ID

    def __init__(self, agent: QLearningAgent):
        self.agent = agent

    def decide(self, envelope: TVEnvelope) -> dict:
        """
        Return a decision dict given a validated TradingView envelope.

        Returns:
            {
                "ql_action":       str,   # EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT
                "state":           str,   # encoded market state
                "execute":         bool,
                "side":            str,   # final side after potential inversion
                "size_multiplier": float,
                "reason":          str,
                "q_value":         float,
            }
        """
        signal = envelope.signal
        params = signal.params

        state    = encode_state(params.dict())
        action   = self.agent.choose_action(state)
        q_values = self.agent.get_q_values(state)
        q_value  = q_values.get(action, 0.0)

        original_side = signal.action  # "buy" | "sell"

        logger.info(
            f"[{signal.symbol}] signal={original_side} | "
            f"state={state} | ql_action={action} | q={q_value:.4f}"
        )

        if action == "EXECUTE_FULL":
            return dict(
                ql_action="EXECUTE_FULL", state=state, execute=True,
                side=original_side, size_multiplier=1.0,
                reason="Q-Learning: execute full position", q_value=q_value,
            )

        if action == "EXECUTE_HALF":
            return dict(
                ql_action="EXECUTE_HALF", state=state, execute=True,
                side=original_side, size_multiplier=0.5,
                reason="Q-Learning: execute half position", q_value=q_value,
            )

        if action == "SKIP":
            return dict(
                ql_action="SKIP", state=state, execute=False,
                side=original_side, size_multiplier=0.0,
                reason="Q-Learning: skip signal", q_value=q_value,
            )

        if action == "INVERT":
            inverted = "sell" if original_side == "buy" else "buy"
            return dict(
                ql_action="INVERT", state=state, execute=True,
                side=inverted, size_multiplier=0.5,
                reason=f"Q-Learning: invert ({original_side}->{inverted})", q_value=q_value,
            )

        # fallback
        return dict(
            ql_action="SKIP", state=state, execute=False,
            side=original_side, size_multiplier=0.0,
            reason=f"Unknown action: {action}", q_value=0.0,
        )
