"""
Q-Learning agent: Q-Table, epsilon-greedy policy, Bellman update, auto-pause.

Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]
"""
import json
import os
import random
import threading
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("bot3.qlearning")

ACTIONS = ["EXECUTE_FULL", "EXECUTE_HALF", "SKIP", "INVERT"]


class QLearningAgent:
    """Online Q-Learning agent for trading decisions."""

    def __init__(self, config: Optional[dict] = None, data_dir: str = "data/qlearning"):
        cfg = config or {}
        self.alpha       = cfg.get("alpha",       float(os.getenv("QLEARNING_ALPHA_INITIAL",   "0.10")))
        self.alpha_min   = cfg.get("alpha_min",   float(os.getenv("QLEARNING_ALPHA_MIN",        "0.02")))
        self.gamma       = cfg.get("gamma",       float(os.getenv("QLEARNING_GAMMA",            "0.90")))
        self.epsilon     = cfg.get("epsilon",     float(os.getenv("QLEARNING_EPSILON_INITIAL",  "0.20")))
        self.epsilon_min = cfg.get("epsilon_min", float(os.getenv("QLEARNING_EPSILON_MIN",      "0.02")))
        self.decay       = cfg.get("decay",       float(os.getenv("QLEARNING_DECAY_PER_TRADE",  "0.999")))

        self._auto_pause_window = int(os.getenv("QLEARNING_AUTO_PAUSE_WINDOW", "20"))
        self._wr_ratio          = float(os.getenv("QLEARNING_AUTO_PAUSE_WR_RATIO", "0.7"))

        self._data_dir   = data_dir
        self._qtable_path = os.path.join(data_dir, "q_table.json")
        self._stats_path  = os.path.join(data_dir, "qlearning_stats.json")

        self._lock           = threading.Lock()
        self.q_table: dict   = {}
        self.paused          = False
        self._recent_rewards: list       = []
        self._baseline_wr: Optional[float] = None

        self._load()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _load(self):
        os.makedirs(self._data_dir, exist_ok=True)
        if os.path.exists(self._qtable_path):
            try:
                with open(self._qtable_path, "r") as f:
                    self.q_table = json.load(f)
                logger.info(f"Q-table loaded ({self._data_dir}): {len(self.q_table)} states")
            except Exception as e:
                logger.warning(f"Q-table load failed ({e}), starting fresh")
                self.q_table = {}

        if os.path.exists(self._stats_path):
            try:
                with open(self._stats_path, "r") as f:
                    stats = json.load(f)
                self.alpha        = stats.get("alpha",       self.alpha)
                self.epsilon      = stats.get("epsilon",     self.epsilon)
                self.paused       = stats.get("paused",      False)
                self._baseline_wr = stats.get("baseline_wr")
                logger.info(f"Stats loaded: alpha={self.alpha:.4f}, eps={self.epsilon:.4f}")
            except Exception as e:
                logger.warning(f"Stats load failed: {e}")

    def save(self):
        """Persist Q-table and stats to disk (thread-safe)."""
        with self._lock:
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._qtable_path, "w") as f:
                json.dump(self.q_table, f, indent=2)
            stats = {
                "alpha":        self.alpha,
                "epsilon":      self.epsilon,
                "gamma":        self.gamma,
                "paused":       self.paused,
                "baseline_wr":  self._baseline_wr,
                "last_updated": datetime.utcnow().isoformat(),
            }
            with open(self._stats_path, "w") as f:
                json.dump(stats, f, indent=2)
        logger.debug("Q-table + stats saved")

    # -------------------------------------------------------------------------
    # Q-table helpers
    # -------------------------------------------------------------------------

    def _get_q(self, state: str) -> dict:
        """Return (lazy-initialising) Q-values for a state."""
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in ACTIONS}
        return self.q_table[state]

    def get_q_values(self, state: str) -> dict:
        """Thread-safe copy of Q-values for a state."""
        with self._lock:
            return dict(self._get_q(state))

    # -------------------------------------------------------------------------
    # Policy
    # -------------------------------------------------------------------------

    def choose_action(self, state: str) -> str:
        """Epsilon-greedy action selection."""
        if self.paused:
            return "SKIP"
        with self._lock:
            if random.random() < self.epsilon:
                return random.choice(ACTIONS)
            q = self._get_q(state)
            return max(q, key=q.get)

    # -------------------------------------------------------------------------
    # Learning
    # -------------------------------------------------------------------------

    def update(self, state: str, action: str, reward: float, next_state: str) -> float:
        """Bellman update. Returns new Q value."""
        with self._lock:
            q_sa     = self._get_q(state)[action]
            max_next = max(self._get_q(next_state).values())
            new_q    = q_sa + self.alpha * (reward + self.gamma * max_next - q_sa)
            self.q_table[state][action] = new_q
            return new_q

    def decay_params(self):
        """Decay alpha and epsilon after each trade."""
        with self._lock:
            self.alpha   = max(self.alpha_min,   self.alpha   * self.decay)
            self.epsilon = max(self.epsilon_min, self.epsilon * self.decay)

    def record_reward(self, reward: float):
        """Track recent rewards for auto-pause evaluation."""
        self._recent_rewards.append(reward)
        if len(self._recent_rewards) > self._auto_pause_window * 2:
            self._recent_rewards = self._recent_rewards[-self._auto_pause_window * 2:]

    def check_degradation(self) -> bool:
        """Return True if recent win rate warrants auto-pause."""
        window = self._recent_rewards[-self._auto_pause_window:]
        if len(window) < self._auto_pause_window:
            return False

        recent_wr = sum(1 for r in window if r > 0) / len(window)

        if self._baseline_wr is None:
            self._baseline_wr = recent_wr
            return False

        threshold = self._baseline_wr * self._wr_ratio
        degraded  = recent_wr < threshold
        if degraded:
            logger.warning(
                f"Degradation: recent_wr={recent_wr:.2%} < "
                f"baseline*ratio={threshold:.2%}"
            )
        return degraded
