"""
Q-Learning trainer: offline replay-buffer training + automatic Q-table backups.

Responsibilities:
  - Append experiences (s, a, r, s', done) to replay_buffer.jsonl
  - Nightly offline re-training (called by DailyRunner)
  - Rotate backups every QLEARNING_BACKUP_INTERVAL_HOURS hours (max 28)
"""
import json
import os
import random
import shutil
import logging
from datetime import datetime
from typing import Optional

from core.qlearning_agent import QLearningAgent

logger = logging.getLogger("bot3.trainer")

MAX_BACKUPS = 28


class QLearningTrainer:
    """Handles offline replay and Q-Table backups."""

    def __init__(self, agent: QLearningAgent, data_dir: str = "data/qlearning"):
        self.agent         = agent
        self._replay_path  = os.path.join(data_dir, "replay_buffer.jsonl")
        self._backup_dir   = os.path.join(data_dir, "backups")
        os.makedirs(self._backup_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Replay buffer
    # -------------------------------------------------------------------------

    def append_experience(
        self,
        state:      str,
        action:     str,
        reward:     float,
        next_state: str,
        done:       bool = False,
    ):
        """Append one (s, a, r, s', done) tuple to the replay buffer."""
        entry = {
            "ts":     datetime.utcnow().isoformat(),
            "s":      state,
            "a":      action,
            "r":      reward,
            "s_next": next_state,
            "done":   done,
        }
        os.makedirs(os.path.dirname(self._replay_path), exist_ok=True)
        with open(self._replay_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def train_from_replay(
        self,
        epochs:          int            = 3,
        max_experiences: Optional[int]  = None,
    ):
        """
        Re-train agent from the full replay buffer (offline passes).
        Called by DailyRunner at end of day.
        """
        if not os.path.exists(self._replay_path):
            logger.info("No replay buffer found - skipping offline training")
            return

        experiences = []
        with open(self._replay_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        experiences.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        if max_experiences:
            experiences = experiences[-max_experiences:]

        logger.info(
            f"Offline training: {len(experiences)} experiences x {epochs} epochs"
        )

        for epoch in range(epochs):
            random.shuffle(experiences)
            for exp in experiences:
                self.agent.update(exp["s"], exp["a"], exp["r"], exp["s_next"])
            self.agent.decay_params()
            logger.debug(f"Epoch {epoch + 1}/{epochs} complete")

        self.agent.save()
        logger.info(
            f"Offline training done. "
            f"alpha={self.agent.alpha:.4f}, eps={self.agent.epsilon:.4f}"
        )

    # -------------------------------------------------------------------------
    # Backups
    # -------------------------------------------------------------------------

    def backup_qtable(self):
        """Create a timestamped backup of q_table.json."""
        src = self.agent._qtable_path
        if not os.path.exists(src):
            return
        ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(self._backup_dir, f"q_table_{ts}.json")
        shutil.copy2(src, dst)
        logger.info(f"Q-table backup created: {dst}")
        self._cleanup_backups()

    def _cleanup_backups(self):
        """Keep only the latest MAX_BACKUPS files."""
        files = sorted(
            f for f in os.listdir(self._backup_dir) if f.startswith("q_table_")
        )
        while len(files) > MAX_BACKUPS:
            os.remove(os.path.join(self._backup_dir, files.pop(0)))

    def save_and_backup(self):
        """Convenience: persist agent then create backup."""
        self.agent.save()
        self.backup_qtable()

    # -------------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------------

    def get_summary(self) -> dict:
        """Return training summary for /qlearning/status and daily report."""
        best  = {"state_action": "N/A", "q": 0.0}
        worst = {"state_action": "N/A", "q": 0.0}

        if self.agent.q_table:
            best_val  = None
            worst_val = None
            for state, actions in self.agent.q_table.items():
                for action, q in actions.items():
                    if best_val is None or q > best_val:
                        best_val = q
                        best = {"state_action": f"{state} -> {action}", "q": round(q, 6)}
                    if worst_val is None or q < worst_val:
                        worst_val = q
                        worst = {"state_action": f"{state} -> {action}", "q": round(q, 6)}

        return {
            "alpha":               round(self.agent.alpha,   6),
            "epsilon":             round(self.agent.epsilon, 6),
            "gamma":               self.agent.gamma,
            "paused":              self.agent.paused,
            "qtable_states":       len(self.agent.q_table),
            "best_state_action":   best["state_action"],
            "worst_state_action":  worst["state_action"],
            "recent_rewards":      self.agent._recent_rewards[-10:],
        }
