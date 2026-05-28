"""Unit tests for QLearningAgent."""
import json
import os
import sys

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_cwd(tmp_path, monkeypatch):
    """Run each test with a fresh temporary working directory."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_init_no_file():
    """Agent initialises with empty Q-table when no file exists."""
    from core.qlearning_agent import QLearningAgent
    agent = QLearningAgent()
    assert isinstance(agent.q_table, dict)
    assert agent.epsilon > 0
    assert agent.alpha   > 0


def test_choose_action_deterministic():
    """With epsilon=0, choose_action always picks the highest-Q action."""
    from core.qlearning_agent import QLearningAgent, ACTIONS

    agent = QLearningAgent(config={"epsilon": 0.0})
    state = "trend_up|mid|bullish"
    agent.q_table[state] = {a: 0.0 for a in ACTIONS}
    agent.q_table[state]["EXECUTE_FULL"] = 5.0

    assert agent.choose_action(state) == "EXECUTE_FULL"


def test_choose_action_explore():
    """With epsilon=1.0, choose_action samples randomly (all actions reachable)."""
    from core.qlearning_agent import QLearningAgent

    agent = QLearningAgent(config={"epsilon": 1.0})
    seen = set()
    for _ in range(200):
        seen.add(agent.choose_action("sideways|low|neutral"))

    assert len(seen) > 1


def test_update_persists(tmp_path):
    """update() + save() writes correct Q-value to disk."""
    from core.qlearning_agent import QLearningAgent

    agent = QLearningAgent(config={"alpha": 0.5, "gamma": 0.9, "epsilon": 0.0})
    state      = "trend_up|mid|bullish"
    next_state = "range|mid|neutral"

    new_q = agent.update(state, "EXECUTE_FULL", reward=1.0, next_state=next_state)
    agent.save()

    assert new_q != 0.0
    qtable_file = os.path.join(str(tmp_path), "data", "qlearning", "q_table.json")
    assert os.path.exists(qtable_file)

    with open(qtable_file) as f:
        loaded = json.load(f)

    assert state in loaded
    assert abs(loaded[state]["EXECUTE_FULL"] - new_q) < 1e-9


def test_decay_params():
    """decay_params() reduces alpha and epsilon but not below minimums."""
    from core.qlearning_agent import QLearningAgent

    agent = QLearningAgent(config={
        "alpha": 0.10, "alpha_min": 0.02,
        "epsilon": 0.20, "epsilon_min": 0.02,
        "decay": 0.5,
    })
    agent.decay_params()
    assert 0.02 <= agent.alpha   < 0.10
    assert 0.02 <= agent.epsilon < 0.20


def test_auto_pause_triggers():
    """Auto-pause triggers when recent win rate drops below threshold."""
    from core.qlearning_agent import QLearningAgent

    cfg = {"alpha": 0.1, "epsilon": 0.0}
    env = {"QLEARNING_AUTO_PAUSE_WINDOW": "5", "QLEARNING_AUTO_PAUSE_WR_RATIO": "0.7"}
    import os
    for k, v in env.items():
        os.environ[k] = v

    agent = QLearningAgent(config=cfg)
    agent._auto_pause_window = 5
    agent._wr_ratio          = 0.7
    agent._baseline_wr       = 0.8   # strong baseline

    # Feed 5 losses
    for _ in range(5):
        agent.record_reward(-1.0)

    assert agent.check_degradation() is True
