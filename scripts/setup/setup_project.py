#!/usr/bin/env python3
"""
setup_project.py - Crea la estructura completa del proyecto bot3-qlearning.

Estructura homologada al patron de bot2 (Trading-agente-01):
  - config.py          : configuracion centralizada
  - sender/            : webhook_client, signal_formatter, telegram_notifier
  - logs/              : reportes JSON por evento + trade_log.xlsx
  - state/             : persistencia (pending_signals, decision_log)
  - excel_logger.py    : registro Excel identico al patron bot2
  - bot3.py            : FastAPI entrypoint que usa el sender layer
  - test_integration.py: prueba end-to-end con bot1
  - run_test_signal.py : dry-run manual sin enviar a bot1

EJECUTAR UNA SOLA VEZ desde la raiz del repositorio:
    python setup_project.py
"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))


def write(path, content):
    """Write content to path (relative to BASE), creating dirs as needed."""
    full = os.path.join(BASE, path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content.lstrip("\n"))
    print(f"  + {path}")


def touch(path):
    """Create empty file."""
    write(path, "")


# =============================================================================
# utils/
# =============================================================================

touch("utils/__init__.py")

write("utils/logger.py", r'''
"""Centralised logger - file + console handlers."""
import logging
import os
from datetime import datetime


def setup_logger(name: str = "bot3") -> logging.Logger:
    """Return a configured logger with file and console handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/bot3_{datetime.utcnow().strftime('%Y%m%d')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
''')

# =============================================================================
# core/
# =============================================================================

touch("core/__init__.py")

write("core/state_encoder.py", r'''
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
''')

write("core/qlearning_agent.py", r'''
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

from core.state_encoder import all_states

logger = logging.getLogger("bot3.qlearning")

ACTIONS = ["EXECUTE_FULL", "EXECUTE_HALF", "SKIP", "INVERT"]

QTABLE_PATH = "data/qlearning/q_table.json"
STATS_PATH  = "data/qlearning/qlearning_stats.json"


class QLearningAgent:
    """Online Q-Learning agent for trading decisions."""

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.alpha       = cfg.get("alpha",       float(os.getenv("QLEARNING_ALPHA_INITIAL",   "0.10")))
        self.alpha_min   = cfg.get("alpha_min",   float(os.getenv("QLEARNING_ALPHA_MIN",        "0.02")))
        self.gamma       = cfg.get("gamma",       float(os.getenv("QLEARNING_GAMMA",            "0.90")))
        self.epsilon     = cfg.get("epsilon",     float(os.getenv("QLEARNING_EPSILON_INITIAL",  "0.20")))
        self.epsilon_min = cfg.get("epsilon_min", float(os.getenv("QLEARNING_EPSILON_MIN",      "0.02")))
        self.decay       = cfg.get("decay",       float(os.getenv("QLEARNING_DECAY_PER_TRADE",  "0.999")))

        self._auto_pause_window = int(os.getenv("QLEARNING_AUTO_PAUSE_WINDOW", "20"))
        self._wr_ratio          = float(os.getenv("QLEARNING_AUTO_PAUSE_WR_RATIO", "0.7"))

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
        os.makedirs("data/qlearning", exist_ok=True)
        if os.path.exists(QTABLE_PATH):
            try:
                with open(QTABLE_PATH, "r") as f:
                    self.q_table = json.load(f)
                logger.info(f"Q-table loaded: {len(self.q_table)} states")
            except Exception as e:
                logger.warning(f"Q-table load failed ({e}), starting fresh")
                self.q_table = {}

        if os.path.exists(STATS_PATH):
            try:
                with open(STATS_PATH, "r") as f:
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
            os.makedirs("data/qlearning", exist_ok=True)
            with open(QTABLE_PATH, "w") as f:
                json.dump(self.q_table, f, indent=2)
            stats = {
                "alpha":        self.alpha,
                "epsilon":      self.epsilon,
                "gamma":        self.gamma,
                "paused":       self.paused,
                "baseline_wr":  self._baseline_wr,
                "last_updated": datetime.utcnow().isoformat(),
            }
            with open(STATS_PATH, "w") as f:
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
''')

write("core/reward_calculator.py", r'''
"""
Reward calculator for Q-Learning agent.

Reward formula (from plan):
    r  = pnl_pct
    r -= 0.05                      # commission + slippage
    r -= 0.1  if duration > 4h
    r -= 0.5  if account_drawdown < -10%
    r += 0.2  if pnl_pct > 0 and r_multiple >= 2
"""
import logging

logger = logging.getLogger("bot3.reward")


def compute_reward(trade_result: dict) -> float:
    """
    Compute reward from a closed trade result.

    Expected keys in trade_result:
        pnl_pct              (float) - gain/loss in percent
        duration_min         (float) - trade duration in minutes
        account_drawdown_pct (float) - account drawdown %  (negative = loss)
        r_multiple           (float, optional) - R multiple achieved
    """
    pnl_pct           = float(trade_result.get("pnl_pct",              0.0))
    duration_min      = float(trade_result.get("duration_min",          0.0))
    drawdown_global   = float(trade_result.get("account_drawdown_pct",  0.0))
    r_multiple        = float(trade_result.get("r_multiple",            0.0))

    r  = pnl_pct
    r -= 0.05                           # commission + slippage

    if duration_min > 240:              # > 4 hours
        r -= 0.1

    if drawdown_global < -10:           # account bleeding
        r -= 0.5

    if pnl_pct > 0 and r_multiple >= 2:
        r += 0.2                        # bonus for high R

    logger.debug(
        f"Reward: pnl={pnl_pct:.3f}% dur={duration_min:.0f}m "
        f"dd={drawdown_global:.1f}% r={r_multiple:.1f}x -> reward={r:.4f}"
    )
    return round(r, 6)
''')

write("core/tv_signal_parser.py", r'''
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
''')

# =============================================================================
# manager/
# =============================================================================

touch("manager/__init__.py")

write("manager/qlearning_trainer.py", r'''
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

REPLAY_BUFFER = "data/qlearning/replay_buffer.jsonl"
BACKUP_DIR    = "data/qlearning/backups"
MAX_BACKUPS   = 28


class QLearningTrainer:
    """Handles offline replay and Q-Table backups."""

    def __init__(self, agent: QLearningAgent):
        self.agent = agent
        os.makedirs(BACKUP_DIR, exist_ok=True)

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
        os.makedirs("data/qlearning", exist_ok=True)
        with open(REPLAY_BUFFER, "a", encoding="utf-8") as f:
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
        if not os.path.exists(REPLAY_BUFFER):
            logger.info("No replay buffer found - skipping offline training")
            return

        experiences = []
        with open(REPLAY_BUFFER, "r", encoding="utf-8") as f:
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
        src = "data/qlearning/q_table.json"
        if not os.path.exists(src):
            return
        ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"q_table_{ts}.json")
        shutil.copy2(src, dst)
        logger.info(f"Q-table backup created: {dst}")
        self._cleanup_backups()

    def _cleanup_backups(self):
        """Keep only the latest MAX_BACKUPS files."""
        files = sorted(
            f for f in os.listdir(BACKUP_DIR) if f.startswith("q_table_")
        )
        while len(files) > MAX_BACKUPS:
            os.remove(os.path.join(BACKUP_DIR, files.pop(0)))

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
''')

# =============================================================================
# strategies/
# =============================================================================

touch("strategies/__init__.py")

write("strategies/strategy_tv_qlearning.py", r'''
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
''')

write("strategies/pinescript/ema_atr_regime_v1.pine", r'''
//@version=5
strategy("EMA ATR Regime - Q-Learning Bot Signal v1",
         overlay=true,
         calc_on_every_tick=false,
         process_orders_on_close=true)

// ===== inputs =====
emaFast   = input.int(20,    "EMA fast")
emaSlow   = input.int(50,    "EMA slow")
atrPeriod = input.int(14,    "ATR period")
adxPeriod = input.int(14,    "ADX period")
adxThr    = input.float(20,  "ADX threshold")
atrMultSL = input.float(1.5, "ATR multiplier (SL)")
rrRatio   = input.float(2.0, "Risk:Reward ratio")
rsiLen    = input.int(14,    "RSI length")

// ===== indicators =====
ef               = ta.ema(close, emaFast)
es               = ta.ema(close, emaSlow)
atr              = ta.atr(atrPeriod)
[diP, diM, adx] = ta.dmi(adxPeriod, adxPeriod)
rsiV             = ta.rsi(close, rsiLen)

// ===== regime =====
regimeStr = adx > adxThr ? (ef > es ? "trend_up" : "trend_down") : "range"

atrP70 = ta.percentile_linear_interpolation(atr, 100, 70)
atrP30 = ta.percentile_linear_interpolation(atr, 100, 30)
volStr = atr > atrP70 ? "high" : (atr < atrP30 ? "low" : "mid")

momStr = rsiV > 55 ? "bullish" : (rsiV < 45 ? "bearish" : "neutral")

// ===== signals =====
longCond  = ta.crossover(ef, es)  and adx > adxThr
shortCond = ta.crossunder(ef, es) and adx > adxThr

// ===== plot =====
plot(ef, color=color.aqua,   title="EMA fast")
plot(es, color=color.orange, title="EMA slow")

// ===== alerts (JSON envelope for /webhook/tv) =====
buildAlert(string sideAct, float entry, float slPx, float tpPx) =>
    '{"timestamp":"' + str.format_time(time, "yyyy-MM-dd'T'HH:mm:ssZ", "UTC") + '",' +
    '"status":"pending","processed":false,"source":"tradingview",' +
    '"signal":{' +
    '"strategy_id":"strategy_tv_qlearning",' +
    '"symbol":"' + syminfo.ticker + '",' +
    '"action":"' + sideAct + '",' +
    '"confidence":0.75,"size":0.1,' +
    '"params":{' +
        '"price":'      + str.tostring(entry) + ',' +
        '"sl":'         + str.tostring(slPx)  + ',' +
        '"tp":'         + str.tostring(tpPx)  + ',' +
        '"atr":'        + str.tostring(atr)   + ',' +
        '"regime":"'    + regimeStr + '",'  +
        '"volatility":"'+ volStr    + '",'  +
        '"momentum":"'  + momStr    + '"'   +
    '}}}'

if longCond
    sl = close - atr * atrMultSL
    tp = close + atr * atrMultSL * rrRatio
    alert(buildAlert("buy", close, sl, tp), alert.freq_once_per_bar_close)
    strategy.entry("L", strategy.long)

if shortCond
    sl = close + atr * atrMultSL
    tp = close - atr * atrMultSL * rrRatio
    alert(buildAlert("sell", close, sl, tp), alert.freq_once_per_bar_close)
    strategy.entry("S", strategy.short)
''')

# =============================================================================
# tests/
# =============================================================================

touch("tests/__init__.py")

write("tests/test_qlearning_agent.py", r'''
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
''')

write("tests/fixtures/tv_envelope_buy.json", r'''{
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
''')

# =============================================================================
# data/ - initial JSON files
# =============================================================================

write("data/qlearning/q_table.json", "{}\n")

write("data/qlearning/qlearning_stats.json", json.dumps({
    "alpha":       0.10,
    "epsilon":     0.20,
    "gamma":       0.90,
    "paused":      False,
    "baseline_wr": None,
    "last_updated": None,
}, indent=2) + "\n")

write("data/bot_status.json", "{}\n")

for _d in ["data/trades", "data/reports", "dashboard/output", "dashboard/history",
           "logs/dry_run", "signals", "data/qlearning/backups"]:
    gk = os.path.join(BASE, _d.replace("/", os.sep), ".gitkeep")
    os.makedirs(os.path.dirname(gk), exist_ok=True)
    if not os.path.exists(gk):
        open(gk, "w").close()
        print(f"  + {_d}/.gitkeep")

# =============================================================================
# scripts/
# =============================================================================

write("scripts/send_tv_signal.ps1", r'''
# send_tv_signal.ps1 - Plan B: envia una senal TV manualmente al endpoint /webhook/tv
# Uso: .\scripts\send_tv_signal.ps1

$url    = "http://localhost:8001/webhook/tv"
$secret = $env:TV_WEBHOOK_SECRET

if (-not $secret) {
    Write-Host "ERROR: TV_WEBHOOK_SECRET no esta definido en el entorno." -ForegroundColor Red
    exit 1
}

$body = @{
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    status    = "pending"
    processed = $false
    source    = "tradingview"
    signal    = @{
        strategy_id = "strategy_tv_qlearning"
        symbol      = "SPY"
        action      = "buy"
        confidence  = 0.75
        size        = 0.1
        params      = @{
            price      = 512.30
            sl         = 510.20
            tp         = 516.50
            atr        = 1.45
            regime     = "trend_up"
            volatility = "mid"
            momentum   = "bullish"
        }
    }
} | ConvertTo-Json -Depth 5

Write-Host "Enviando senal a $url ..." -ForegroundColor Cyan

$response = Invoke-RestMethod `
    -Uri     $url `
    -Method  POST `
    -Headers @{"Content-Type" = "application/json"; "X-Webhook-Secret" = $secret} `
    -Body    $body

$response | ConvertTo-Json -Depth 5
''')

write("scripts/restore_qtable.ps1", r'''
# restore_qtable.ps1 - Restaura la Q-Table desde un backup
# Uso: .\scripts\restore_qtable.ps1 -BackupFile "data\qlearning\backups\q_table_20260503_120000.json"

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

$target = "data\qlearning\q_table.json"

if (-not (Test-Path $BackupFile)) {
    Write-Host "ERROR: Backup no encontrado: $BackupFile" -ForegroundColor Red
    exit 1
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path $target) {
    Copy-Item $target "data\qlearning\q_table_pre_restore_$ts.json"
    Write-Host "Backup previo guardado como q_table_pre_restore_$ts.json" -ForegroundColor Yellow
}

Copy-Item $BackupFile $target
Write-Host "Q-Table restaurada desde: $BackupFile" -ForegroundColor Green
Write-Host "Reinicia el bot para cargar la nueva Q-Table." -ForegroundColor Cyan
''')

# =============================================================================
# docs/
# =============================================================================

write("docs/qlearning_strategy.md", r'''
# Q-Learning Strategy - bot3

## Filosofia

El agente Q-Learning aprende a filtrar y modificar senales de TradingView para
maximizar el rendimiento a largo plazo. En lugar de ejecutar ciegamente cada
alerta, el agente decide la accion optima basandose en el estado del mercado
(regimen + volatilidad + momentum) y su experiencia acumulada.

## Estados (s) - 27 combinaciones

| Dimension  | Valores                              | Origen en PineScript           |
|------------|--------------------------------------|--------------------------------|
| regime     | trend_up \| trend_down \| range      | ADX + EMA fast/slow crossover  |
| volatility | low \| mid \| high                   | ATR percentil (30/70) 100 velas|
| momentum   | bullish \| bearish \| neutral        | RSI(14) thresholds 45/55       |

**Clave:** `"trend_up|mid|bullish"`

## Acciones (a)

| Accion        | Comportamiento                                          |
|---------------|---------------------------------------------------------|
| EXECUTE_FULL  | Tomar la senal con el size recibido (x1.0)              |
| EXECUTE_HALF  | Tomar la senal con size * 0.5                           |
| SKIP          | No ejecutar - responde `skipped_by_qlearning`           |
| INVERT        | Ejecutar la operacion contraria con size * 0.5          |

## Recompensa (r)

```
r  = pnl_pct
r -= 0.05                       # comision + slippage
r -= 0.10  si duracion > 4h
r -= 0.50  si drawdown_cuenta < -10%
r += 0.20  si pnl_pct > 0 y r_multiple >= 2
```

## Actualizacion Q-Table (Bellman)

```
Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]
```

## Hiperparametros iniciales

| Parametro           | Valor | Min  | Decay       |
|---------------------|-------|------|-------------|
| alpha (learning)    | 0.10  | 0.02 | x0.999/trade|
| gamma (descuento)   | 0.90  | -    | fijo        |
| epsilon (exploracion)| 0.20 | 0.02 | x0.999/trade|

## Auto-pausa por degradacion

Cada 20 trades se evalua la ventana movil:
- Si `win_rate_reciente < win_rate_baseline * 0.70` el agente se auto-pausa.
- Se notifica por Telegram (si esta configurado).
- Se puede reactivar via `POST /qlearning/resume`.

## Flujo completo

```
TradingView alert
    |
    v
POST /webhook/tv  (X-Webhook-Secret header)
    |
    +--> parse_tv_envelope()
    +--> encode_state(regime, volatility, momentum)
    +--> agent.choose_action(state)   [epsilon-greedy]
    |
    +-- EXECUTE_FULL  -> OrderRouter.place_order(size x1.0)
    +-- EXECUTE_HALF  -> OrderRouter.place_order(size x0.5)
    +-- SKIP          -> log + return skipped_by_qlearning
    +-- INVERT        -> OrderRouter.place_order(side invertido, x0.5)
    |
    v
pending_q_decisions[order_id] = {state, action, timestamp}
    |
    v  (cuando la posicion se cierra - Alpaca poll o alerta manual)
POST /qlearning/update  {order_id, pnl_pct, duration_min, ...}
    |
    +--> compute_reward(trade_result)
    +--> agent.update(s, a, r, s_next)
    +--> agent.decay_params()
    +--> trainer.append_experience(...)
    +--> agent.save()
```

## Monitoreo

- `GET /qlearning/status` - resumen: alpha, epsilon, paused, best/worst state-action
- `GET /qlearning/qtable` - Q-table completa (JSON)
- `GET /pending`           - decisiones pendientes de cierre

## Intervencion manual

```bash
# Pausar agente
curl -X POST http://localhost:8001/qlearning/pause

# Reanudar agente
curl -X POST http://localhost:8001/qlearning/resume

# Restaurar Q-Table desde backup (PowerShell)
.\scripts\restore_qtable.ps1 -BackupFile "data\qlearning\backups\q_table_20260503_120000.json"

# Resetear Q-Table (tabla vacia)
echo {} > data\qlearning\q_table.json
```
''')

write("docs/api_reference.md", r'''
# API Reference - bot3-qlearning

Base URL: `http://localhost:8001`

## Endpoints existentes

### `GET /`
Health check rapido.

### `GET /health`
Estado detallado: dry_run, paused, epsilon, alpha, pending_decisions.

---

## Endpoint nuevo: TradingView Webhook

### `POST /webhook/tv`

Recibe alertas de TradingView y las procesa con el agente Q-Learning.

**Headers requeridos:**
```
Content-Type:    application/json
X-Webhook-Secret: <TV_WEBHOOK_SECRET>
```

**Body:** ver `docs/webhook_format.md`

**Respuestas:**

| HTTP | status                   | Significado                                      |
|------|--------------------------|--------------------------------------------------|
| 200  | executed / executed_dry_run | Q-Learning eligio EXECUTE_FULL o HALF         |
| 200  | skipped_by_qlearning     | Q-Learning decidio SKIP                          |
| 200  | inverted_by_qlearning    | Q-Learning ejecuto la operacion contraria         |
| 200  | rejected                 | Agente pausado                                   |
| 200  | received_no_signal_tv    | status != "pending", no se tomo accion           |
| 400  | -                        | JSON invalido                                    |
| 401  | -                        | X-Webhook-Secret incorrecto                      |
| 403  | -                        | IP no permitida (si TV_ENFORCE_IP_WHITELIST=true)|
| 422  | -                        | Campos faltantes o invalidos en el envelope      |

---

## Endpoints Q-Learning

### `GET /qlearning/status`
Resumen del agente: alpha, epsilon, paused, best/worst state-action, recent rewards.

### `GET /qlearning/qtable`
Q-table completa en JSON.

### `POST /qlearning/update`
Aplica aprendizaje hindsight cuando una posicion se cierra.

**Body:**
```json
{
  "order_id":              "dry_SPY_20260503_143000000000",
  "pnl_pct":              1.25,
  "duration_min":         45.0,
  "account_drawdown_pct": -2.5,
  "r_multiple":           2.1,
  "next_state":           "range|mid|neutral"
}
```

### `POST /qlearning/pause`  /  `POST /qlearning/resume`
Pausa o reactiva el agente manualmente.

### `GET /pending`
Decisiones pendientes de cierre de posicion.
''')

write("docs/webhook_format.md", r'''
# Webhook Format

## Formato TradingView (`/webhook/tv`)

El envelope sigue la misma filosofia que el envelope de Claude Routines.

**Header:**
```
X-Webhook-Secret: <valor de TV_WEBHOOK_SECRET en .env>
```

**Body:**
```json
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
```

**Campos `params` validos:**

| Campo      | Tipo  | Valores validos                             |
|------------|-------|---------------------------------------------|
| price      | float | precio de entrada                           |
| sl         | float | stop loss                                   |
| tp         | float | take profit                                 |
| atr        | float | ATR en el momento de la senal               |
| regime     | str   | trend_up \| trend_down \| range             |
| volatility | str   | low \| mid \| high                          |
| momentum   | str   | bullish \| bearish \| neutral               |

El bot ignora silenciosamente envelopes con `status != "pending"`.
''')

# =============================================================================
# config.py  (patron bot2 - config centralizado en raiz)
# =============================================================================

write("config.py", r'''
"""
config.py - Configuracion centralizada de bot3-qlearning.

Patron identico a bot2: todas las variables en un solo modulo.
Carga automaticamente .env si python-dotenv esta instalado.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -- Bot3 server ---------------------------------------------------------------
PORT = int(os.getenv("PORT", "8001"))

# -- TradingView webhook -------------------------------------------------------
TV_WEBHOOK_SECRET   = os.getenv("TV_WEBHOOK_SECRET", "")
TV_ALLOWED_IPS      = [
    ip.strip()
    for ip in os.getenv("TV_ALLOWED_IPS", "").split(",")
    if ip.strip()
]
TV_ENFORCE_IP       = os.getenv("TV_ENFORCE_IP_WHITELIST", "false").lower() == "true"

# -- Bot1 integration (patron identico a bot2) ---------------------------------
# bot2 usa: http://127.0.0.1:8000/webhook/bot2
# bot3 usa: http://127.0.0.1:8000/webhook/bot3
WEBHOOK_URL         = os.getenv("BOT1_WEBHOOK_URL", "http://127.0.0.1:8000/webhook/bot3")
WEBHOOK_SECRET      = os.getenv("BOT1_WEBHOOK_SECRET", "")

# -- Telegram ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")

# -- Runtime -------------------------------------------------------------------
DRY_RUN             = os.getenv("DRY_RUN", "true").lower() == "true"
QLEARNING_ENABLED   = os.getenv("QLEARNING_ENABLED", "true").lower() == "true"

# -- Q-Learning hiperparametros ------------------------------------------------
QLEARNING_ALPHA_INITIAL          = float(os.getenv("QLEARNING_ALPHA_INITIAL",         "0.10"))
QLEARNING_ALPHA_MIN              = float(os.getenv("QLEARNING_ALPHA_MIN",             "0.02"))
QLEARNING_GAMMA                  = float(os.getenv("QLEARNING_GAMMA",                 "0.90"))
QLEARNING_EPSILON_INITIAL        = float(os.getenv("QLEARNING_EPSILON_INITIAL",       "0.20"))
QLEARNING_EPSILON_MIN            = float(os.getenv("QLEARNING_EPSILON_MIN",           "0.02"))
QLEARNING_DECAY_PER_TRADE        = float(os.getenv("QLEARNING_DECAY_PER_TRADE",       "0.999"))
QLEARNING_BACKUP_INTERVAL_HOURS  = int(os.getenv("QLEARNING_BACKUP_INTERVAL_HOURS",   "6"))
QLEARNING_AUTO_PAUSE_WINDOW      = int(os.getenv("QLEARNING_AUTO_PAUSE_WINDOW",       "20"))
QLEARNING_AUTO_PAUSE_WR_RATIO    = float(os.getenv("QLEARNING_AUTO_PAUSE_WR_RATIO",   "0.7"))

# -- Paths (relativos a la raiz del proyecto) ----------------------------------
STATE_DIR           = "state"
LOGS_DIR            = "logs"
DATA_DIR            = "data"
''')

# =============================================================================
# sender/  (patron identico a bot2: __init__, webhook_client, signal_formatter,
#                                   telegram_notifier)
# =============================================================================

touch("sender/__init__.py")

write("sender/webhook_client.py", r'''
"""
webhook_client.py - Envia senales a bot1 (patron identico a bot2).

Flujo:
  send(payload) -> POST bot1/webhook/bot3 con backoff 3 intentos
  retry_pending() -> reintenta pending_signals.json al inicio de ciclo

Estado: state/pending_signals.json
"""
import json
import logging
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger("bot3.webhook")

_MAX_RETRIES  = 3
_PENDING_FILE = Path("state") / "pending_signals.json"


def _load_pending() -> list:
    try:
        return json.loads(_PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_pending(signals: list) -> None:
    _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PENDING_FILE.write_text(json.dumps(signals, indent=2), encoding="utf-8")


def _save_to_pending(payload: dict) -> None:
    signals = _load_pending()
    signals.append(payload)
    _save_pending(signals)
    logger.info(f"Senal guardada como pendiente (total: {len(signals)})")


def _post(payload: dict, headers: dict) -> dict:
    """Envia con backoff exponencial. Retorna el resultado."""
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.post(
                config.WEBHOOK_URL,
                json=payload,
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            response = r.json()
            logger.info(f"Webhook OK (intento {attempt}): status={response.get('status')}")
            return response
        except requests.exceptions.ConnectionError as e:
            last_error = str(e)
            logger.warning(f"Intento {attempt}/{_MAX_RETRIES} - bot1 no disponible")
        except requests.exceptions.Timeout:
            last_error = "timeout"
            logger.warning(f"Intento {attempt}/{_MAX_RETRIES} - timeout")
        except requests.exceptions.HTTPError:
            logger.error(f"HTTP {r.status_code} de bot1: {r.text[:200]}")
            return {"status": "error", "http_code": r.status_code, "detail": r.text}
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error inesperado en webhook: {e}")

        if attempt < _MAX_RETRIES:
            time.sleep(5 * attempt)  # backoff: 5s, 10s, 15s

    return {"status": "failed", "error": last_error}


def send(payload: dict) -> dict:
    """Envia el payload a bot1. Maneja dry_run, rejected y fallos de red."""
    if config.DRY_RUN:
        symbol = (payload.get("signal") or {}).get("symbol", "?")
        action = (payload.get("signal") or {}).get("action", "?")
        logger.info(f"[DRY_RUN] Webhook NO enviado - {action.upper()} {symbol}")
        return {"status": "dry_run"}

    headers = {
        "Content-Type":    "application/json",
        "X-Webhook-Secret": config.WEBHOOK_SECRET,
    }
    response = _post(payload, headers)

    if isinstance(response, dict) and response.get("status") == "rejected":
        reason = response.get("reason", "sin razon")
        logger.warning(f"bot1 rechazo la senal: {reason}")
        return response

    if isinstance(response, dict) and response.get("status") == "received_no_signal":
        logger.info("bot1 confirmo recepcion de no_signal")
        return response

    if isinstance(response, dict) and response.get("status") == "failed":
        if payload.get("status") == "pending":
            _save_to_pending(payload)

    return response


def retry_pending() -> int:
    """Reintenta senales pendientes al inicio. Retorna cuantas se enviaron."""
    signals = _load_pending()
    if not signals:
        return 0

    logger.info(f"Reintentando {len(signals)} senal(es) pendiente(s)...")
    headers = {
        "Content-Type":    "application/json",
        "X-Webhook-Secret": config.WEBHOOK_SECRET,
    }
    remaining  = []
    sent_count = 0
    for payload in signals:
        response = _post(payload, headers)
        if isinstance(response, dict) and response.get("status") not in ("failed", "error"):
            sent_count += 1
        else:
            remaining.append(payload)

    _save_pending(remaining)
    if sent_count:
        logger.info(f"{sent_count} senal(es) pendiente(s) enviada(s) OK")
    return sent_count
''')

write("sender/signal_formatter.py", r'''
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
''')

write("sender/telegram_notifier.py", r'''
"""
telegram_notifier.py - Notificaciones Telegram (patron identico a bot2).

Funciones:
  signal_sent()     -> senal aprobada y ejecutada en bot1
  signal_rejected() -> bot1 rechazo la senal
  webhook_failed()  -> fallo de red, senal en cola
  signal_skipped()  -> Q-Learning descarto la senal (SKIP)
  agent_paused()    -> auto-pausa activada
  startup()         -> bot3 arrancado
"""
import logging
import requests

import config

logger = logging.getLogger("bot3.telegram")

_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def _send(text: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            _BASE,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        logger.debug(f"Telegram error (no critico): {e}")


def signal_sent(symbol: str, action: str, size: float, ql_action: str, state: str, dry_run: bool):
    mode = "DRY" if dry_run else "LIVE"
    _send(
        f"* <b>[BOT3 {mode}] Senal enviada a bot1</b>\n"
        f"  Simbolo  : {symbol}\n"
        f"  Accion   : {action.upper()}\n"
        f"  Tamano   : {size:.1%}\n"
        f"  QL Action: {ql_action}\n"
        f"  Estado   : {state}"
    )


def signal_rejected(symbol: str, reason: str):
    _send(
        f"* <b>[BOT3] Senal RECHAZADA por bot1</b>\n"
        f"  Simbolo: {symbol}\n"
        f"  Razon  : {reason}"
    )


def webhook_failed(symbol: str, error: str):
    _send(
        f"* <b>[BOT3] Fallo de red - senal en cola</b>\n"
        f"  Simbolo: {symbol}\n"
        f"  Error  : {error[:100]}"
    )


def signal_skipped(symbol: str, ql_action: str, state: str, q_value: float):
    _send(
        f"🔍 <b>[BOT3] Senal DESCARTADA por Q-Learning</b>\n"
        f"  Simbolo : {symbol}\n"
        f"  Accion  : {ql_action}\n"
        f"  Estado  : {state}\n"
        f"  Q-value : {q_value:.4f}"
    )


def agent_paused(reason: str):
    _send(
        f"🛑 <b>[BOT3] Agente Q-Learning AUTO-PAUSADO</b>\n"
        f"  Razon: {reason}"
    )


def startup(dry_run: bool, port: int):
    mode = "DRY RUN" if dry_run else "* LIVE"
    _send(
        f"🚀 <b>[BOT3] Bot3 Q-Learning arrancado</b>\n"
        f"  Modo  : {mode}\n"
        f"  Puerto: {port}\n"
        f"  URL   : http://localhost:{port}/webhook/tv"
    )
''')

# =============================================================================
# excel_logger.py  (patron identico a bot2, en la raiz del proyecto)
# =============================================================================

write("excel_logger.py", r'''
"""
excel_logger.py - Registro Excel de todas las decisiones (patron bot2).

Una fila por senal recibida. Escribe/acumula en logs/trade_log.xlsx.
Si el archivo esta abierto en Excel, advierte sin crashear el bot.
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger("bot3.excel")

EXCEL_PATH = os.path.join("logs", "trade_log.xlsx")

COLUMNS = [
    "timestamp_utc",
    "event_id",
    "mode",
    "symbol",
    "tv_action",
    "ql_action",
    "ql_state",
    "q_value",
    "regime",
    "volatility",
    "momentum",
    "price",
    "sl",
    "tp",
    "atr",
    "execute",
    "final_action",
    "size",
    "confidence",
    "webhook_status",
    "order_id",
    "reason",
    "epsilon",
    "alpha",
]


def append_excel_rows(rows: list) -> None:
    """
    Acumula filas en logs/trade_log.xlsx.
    Crea el archivo si no existe. Agrega filas si ya existe.
    """
    if not rows:
        return

    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl no instalado - Excel logging desactivado")
        return

    os.makedirs("logs", exist_ok=True)

    try:
        if os.path.exists(EXCEL_PATH):
            wb = openpyxl.load_workbook(EXCEL_PATH)
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "bot3_decisions"
            ws.append(COLUMNS)

        for row in rows:
            ws.append([row.get(col, "") for col in COLUMNS])

        wb.save(EXCEL_PATH)
        logger.debug(f"Excel actualizado: +{len(rows)} fila(s) -> {EXCEL_PATH}")

    except PermissionError:
        logger.warning(f"Excel abierto en otro programa - no se pudo escribir: {EXCEL_PATH}")
    except Exception as e:
        logger.error(f"Error escribiendo Excel: {e}")
''')

# =============================================================================
# state/  (persistencia - patron bot2: pending_signals, decision_log)
# =============================================================================

write("state/.gitkeep", "")
write("state/pending_signals.json", "[]")
write("state/decision_log.jsonl",  "")

# =============================================================================
# logs/  (reportes JSON por evento + trade_log.xlsx)
# =============================================================================

write("logs/.gitkeep", "")

# =============================================================================
# bot3.py  (entrypoint principal - patron bot2, usa sender layer)
# =============================================================================

write("bot3.py", r'''
"""
bot3.py - FastAPI entrypoint para Trading Bot 3 (Q-Learning).

Patron identico a bot2 (agente01.py):
  - Recibe alertas TradingView en /webhook/tv
  - Aplica Q-Learning para decidir accion
  - Envia senal a bot1 via sender/webhook_client.py  (POST /webhook/bot3)
  - Notifica via Telegram (sender/telegram_notifier.py)
  - Registra en state/decision_log.jsonl
  - Escribe reporte en logs/YYYY-MM-DD_HH-MM-SS.json
  - Acumula en logs/trade_log.xlsx (excel_logger.py)

Endpoints:
    GET  /                   health check rapido
    GET  /health             estado detallado
    POST /webhook/tv         senales TradingView -> Q-Learning -> bot1
    GET  /qlearning/status   estadisticas del agente
    GET  /qlearning/qtable   Q-table completa
    POST /qlearning/update   aprendizaje hindsight (posicion cerrada)
    POST /qlearning/pause    pausar agente
    POST /qlearning/resume   reanudar agente
    GET  /pending            decisiones pendientes de actualizacion Q
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel

from core.qlearning_agent      import QLearningAgent
from core.reward_calculator    import compute_reward
from core.tv_signal_parser     import parse_tv_envelope
from excel_logger              import append_excel_rows
from manager.qlearning_trainer import QLearningTrainer
from sender                    import webhook_client, signal_formatter, telegram_notifier
from strategies.strategy_tv_qlearning import TVQLearningStrategy
from utils.logger              import setup_logger

logger = setup_logger("bot3")

# -- globals -------------------------------------------------------------------

agent:    Optional[QLearningAgent]      = None
trainer:  Optional[QLearningTrainer]   = None
strategy: Optional[TVQLearningStrategy] = None

# {order_id: {state, action, timestamp, ticker, original_side, executed_side}}
pending_q_decisions: dict = {}

# -- helpers de persistencia (patron bot2) -------------------------------------

_DECISION_LOG = Path("state") / "decision_log.jsonl"


def _log_decision(entry: dict) -> None:
    """Append una decision a state/decision_log.jsonl."""
    _DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    try:
        with open(_DECISION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"No se pudo escribir decision_log: {e}")


def _write_event_report(report: dict) -> None:
    """Escribe un reporte JSON en logs/YYYY-MM-DD_HH-MM-SS.json."""
    Path("logs").mkdir(parents=True, exist_ok=True)
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    fpath   = Path("logs") / f"{ts}.json"
    try:
        fpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"No se pudo escribir reporte: {e}")


def _build_excel_row(
    event_id: str,
    symbol: str,
    tv_action: str,
    decision: dict,
    execute: bool,
    webhook_status: str,
    order_id: str,
    envelope_signal,
) -> dict:
    params = envelope_signal.params
    return {
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "event_id":       event_id,
        "mode":           "DRY_RUN" if config.DRY_RUN else "LIVE",
        "symbol":         symbol,
        "tv_action":      tv_action,
        "ql_action":      decision.get("ql_action", ""),
        "ql_state":       decision.get("state", ""),
        "q_value":        round(decision.get("q_value", 0.0), 6),
        "regime":         params.regime,
        "volatility":     params.volatility,
        "momentum":       params.momentum,
        "price":          params.price,
        "sl":             params.sl,
        "tp":             params.tp,
        "atr":            params.atr,
        "execute":        execute,
        "final_action":   decision.get("side", "none") if execute else "none",
        "size":           envelope_signal.size * decision.get("size_multiplier", 0.0),
        "confidence":     envelope_signal.confidence,
        "webhook_status": webhook_status,
        "order_id":       order_id,
        "reason":         decision.get("reason", ""),
        "epsilon":        round(agent.epsilon, 6) if agent else "",
        "alpha":          round(agent.alpha,   6) if agent else "",
    }


# -- lifespan ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, trainer, strategy

    # Crear directorios necesarios
    for d in ("logs", "state", "data/qlearning"):
        Path(d).mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Arrancando bot3 - DRY_RUN={config.DRY_RUN}, "
        f"QLEARNING={config.QLEARNING_ENABLED}, PORT={config.PORT}"
    )

    # Reintentar senales pendientes de ciclos anteriores (patron bot2)
    retried = webhook_client.retry_pending()
    if retried:
        logger.info(f"Senales pendientes reintentadas al inicio: {retried}")

    if config.QLEARNING_ENABLED:
        agent    = QLearningAgent()
        trainer  = QLearningTrainer(agent)
        strategy = TVQLearningStrategy(agent)
        logger.info(
            f"Q-Learning inicializado: eps={agent.epsilon:.4f} "
            f"alpha={agent.alpha:.4f} paused={agent.paused}"
        )

    telegram_notifier.startup(config.DRY_RUN, config.PORT)

    yield

    if agent:
        agent.save()
        logger.info("Q-table guardada al cerrar")


app = FastAPI(
    title="Trading Bot 3 - Q-Learning",
    version="1.0.0",
    lifespan=lifespan,
)

# -- helpers de seguridad ------------------------------------------------------


def _check_ip(request: Request):
    if not config.TV_ENFORCE_IP:
        return
    client_ip = request.client.host if request.client else ""
    if client_ip not in config.TV_ALLOWED_IPS:
        raise HTTPException(status_code=403, detail=f"IP no permitida: {client_ip}")


def _check_secret(secret: Optional[str]):
    if not config.TV_WEBHOOK_SECRET:
        logger.warning("TV_WEBHOOK_SECRET no configurado - aceptando todo (INSEGURO)")
        return
    if secret != config.TV_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Webhook secret invalido")


# -- routes --------------------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "bot": "bot3-qlearning", "version": "1.0.0"}


@app.get("/health")
def health():
    return {
        "status":            "ok",
        "dry_run":           config.DRY_RUN,
        "qlearning_enabled": config.QLEARNING_ENABLED,
        "agent_paused":      agent.paused   if agent else None,
        "epsilon":           round(agent.epsilon, 4) if agent else None,
        "alpha":             round(agent.alpha,   4) if agent else None,
        "pending_decisions": len(pending_q_decisions),
        "webhook_url":       config.WEBHOOK_URL,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }


@app.post("/webhook/tv")
async def webhook_tv(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Recibe alertas TradingView, aplica Q-Learning y envia a bot1.
    Patron identico a bot2: log + Excel + Telegram por cada evento.
    """
    _check_ip(request)
    _check_secret(x_webhook_secret)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")

    logger.info(
        f"TV webhook recibido: source={body.get('source')} "
        f"status={body.get('status')}"
    )

    # Reconocer envelopes que no son pending (sin accion)
    if body.get("status") != "pending":
        return {
            "status":    "received_no_signal_tv",
            "detail":    f"status={body.get('status')} - sin accion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        envelope = parse_tv_envelope(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Envelope invalido: {e}")

    signal          = envelope.signal
    ticker          = signal.symbol
    original_action = signal.action
    params          = signal.params

    # -- Q-Learning decision ---------------------------------------------------
    if not agent or not strategy:
        decision = {
            "ql_action":       "EXECUTE_FULL",
            "state":           "unknown",
            "execute":         True,
            "side":            original_action,
            "size_multiplier": 1.0,
            "reason":          "Q-Learning desactivado - ejecutando senal original",
            "q_value":         0.0,
        }
    else:
        decision = strategy.decide(envelope)

    ql_action       = decision["ql_action"]
    execute         = decision["execute"]
    side            = decision["side"]
    size_multiplier = decision["size_multiplier"]
    state           = decision["state"]
    q_value         = decision.get("q_value", 0.0)
    final_size      = round(signal.size * size_multiplier, 4)

    event_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    # -- Si Q-Learning descarta la senal --------------------------------------
    if not execute:
        logger.info(f"[{ticker}] Senal descartada por Q-Learning: {ql_action}")
        telegram_notifier.signal_skipped(ticker, ql_action, state, q_value)

        log_entry = {
            "event_id":  event_id,
            "decision":  "SKIP",
            "ql_action": ql_action,
            "symbol":    ticker,
            "state":     state,
            "q_value":   q_value,
            "reason":    decision["reason"],
        }
        _log_decision(log_entry)

        excel_row = _build_excel_row(
            event_id, ticker, original_action, decision, False, "skipped", "", signal
        )
        background_tasks.add_task(append_excel_rows, [excel_row])
        background_tasks.add_task(_write_event_report, {**log_entry, "dry_run": config.DRY_RUN})

        return {
            "ticker":          ticker,
            "original_action": original_action,
            "ql_action":       ql_action,
            "state":           state,
            "q_value":         q_value,
            "execute":         False,
            "status":          "skipped_by_qlearning",
            "reason":          decision["reason"],
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

    # -- Construir payload para bot1 (patron bot2) -----------------------------
    payload = signal_formatter.build_payload(
        symbol     = ticker,
        action     = side,
        confidence = signal.confidence,
        size       = final_size,
        ql_action  = ql_action,
        ql_state   = state,
        q_value    = q_value,
        regime     = params.regime,
        volatility = params.volatility,
        momentum   = params.momentum,
        price      = params.price,
        sl         = params.sl,
        tp         = params.tp,
        atr        = params.atr,
    )

    # -- Enviar a bot1 (patron bot2: send + manejo de respuesta) --------------
    wh_response     = webhook_client.send(payload)
    webhook_status  = wh_response.get("status", "unknown")
    order_id        = wh_response.get("order_id", event_id)

    if webhook_status == "dry_run":
        order_id = f"dry_{ticker}_{event_id}"
        logger.info(f"[{ticker}] DRY_RUN - senal simulada: {ql_action} {side} size={final_size}")
        telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, True)

    elif webhook_status == "executed":
        logger.info(f"[{ticker}] bot1 ejecuto: {side} size={final_size} order={order_id}")
        telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, False)

    elif webhook_status == "rejected":
        reason = wh_response.get("reason", "sin razon")
        logger.warning(f"[{ticker}] bot1 rechazo: {reason}")
        telegram_notifier.signal_rejected(ticker, reason)

    elif webhook_status == "failed":
        error = wh_response.get("error", "error de red")
        logger.error(f"[{ticker}] Fallo de red - senal en cola: {error}")
        telegram_notifier.webhook_failed(ticker, error)

    # -- Tracking para hindsight learning --------------------------------------
    if agent and webhook_status in ("dry_run", "executed"):
        pending_q_decisions[order_id] = {
            "state":         state,
            "action":        ql_action,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "ticker":        ticker,
            "original_side": original_action,
            "executed_side": side,
        }

    # -- Persistencia (patron bot2: decision_log + Excel + reporte) -----------
    log_entry = {
        "event_id":      event_id,
        "decision":      "EXECUTE" if webhook_status in ("dry_run", "executed") else "FAILED",
        "ql_action":     ql_action,
        "symbol":        ticker,
        "action":        side,
        "state":         state,
        "q_value":       q_value,
        "size":          final_size,
        "webhook_status": webhook_status,
        "order_id":      order_id,
        "reason":        decision["reason"],
        "dry_run":       config.DRY_RUN,
    }
    _log_decision(log_entry)

    excel_row = _build_excel_row(
        event_id, ticker, original_action, decision, True, webhook_status, order_id, signal
    )
    background_tasks.add_task(append_excel_rows, [excel_row])
    background_tasks.add_task(_write_event_report, log_entry)

    if trainer:
        background_tasks.add_task(trainer.save_and_backup)

    return {
        "ticker":          ticker,
        "original_action": original_action,
        "ql_action":       ql_action,
        "state":           state,
        "q_value":         q_value,
        "execute":         True,
        "side":            side,
        "size":            final_size,
        "status":          webhook_status,
        "order_id":        order_id,
        "dry_run":         config.DRY_RUN,
        "reason":          decision["reason"],
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }


@app.get("/qlearning/status")
def qlearning_status():
    if not agent:
        return {"error": "Q-Learning no activado"}
    return trainer.get_summary() if trainer else {"paused": agent.paused}


@app.get("/qlearning/qtable")
def get_qtable():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    return {"q_table": agent.q_table, "states": len(agent.q_table)}


class UpdateRequest(BaseModel):
    order_id:             str
    pnl_pct:              float
    duration_min:         float = 0.0
    account_drawdown_pct: float = 0.0
    r_multiple:           float = 0.0
    next_state:           Optional[str] = None


@app.post("/qlearning/update")
async def manual_update(req: UpdateRequest):
    """Aprendizaje hindsight cuando una posicion se cierra."""
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")

    if req.order_id not in pending_q_decisions:
        raise HTTPException(
            status_code=404,
            detail=f"Order '{req.order_id}' no encontrada en decisiones pendientes",
        )

    pending    = pending_q_decisions.pop(req.order_id)
    state      = pending["state"]
    action     = pending["action"]

    trade_result = {
        "pnl_pct":              req.pnl_pct,
        "duration_min":         req.duration_min,
        "account_drawdown_pct": req.account_drawdown_pct,
        "r_multiple":           req.r_multiple,
    }
    reward     = compute_reward(trade_result)
    next_state = req.next_state or state

    new_q = agent.update(state, action, reward, next_state)
    agent.decay_params()
    agent.record_reward(reward)

    if agent.check_degradation():
        agent.paused = True
        logger.warning("Auto-pausa activada por degradacion de rendimiento")
        telegram_notifier.agent_paused(f"win_rate bajo umbral en {agent._auto_pause_window} trades")

    if trainer:
        trainer.append_experience(state, action, reward, next_state)

    agent.save()

    _log_decision({
        "event_id": f"update_{req.order_id}",
        "decision": "HINDSIGHT_UPDATE",
        "state":    state,
        "action":   action,
        "reward":   reward,
        "new_q":    round(new_q, 6),
        "pnl_pct":  req.pnl_pct,
    })

    return {
        "order_id":    req.order_id,
        "state":       state,
        "action":      action,
        "pnl_pct":     req.pnl_pct,
        "reward":      reward,
        "new_q_value": round(new_q, 6),
        "next_state":  next_state,
        "agent_paused": agent.paused,
        "alpha":       round(agent.alpha,   6),
        "epsilon":     round(agent.epsilon, 6),
    }


@app.get("/pending")
def get_pending():
    return {"pending": pending_q_decisions, "count": len(pending_q_decisions)}


@app.post("/qlearning/pause")
def pause_agent():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    agent.paused = True
    agent.save()
    return {"status": "paused"}


@app.post("/qlearning/resume")
def resume_agent():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    agent.paused = False
    agent.save()
    return {"status": "resumed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, reload=False)
''')

# =============================================================================
# dashboard/
# =============================================================================

write("dashboard/generate_dashboard.py", r'''
"""
Dashboard generator - produces an HTML report for the trading bot.
Includes a Q-Learning Insights section.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("bot3.dashboard")

QTABLE_PATH = "data/qlearning/q_table.json"
STATS_PATH  = "data/qlearning/qlearning_stats.json"
OUTPUT_DIR  = "dashboard/output"
ACTIONS     = ["EXECUTE_FULL", "EXECUTE_HALF", "SKIP", "INVERT"]


def _load_json(path: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _build_qlearning_section(q_table: dict, stats: dict) -> str:
    """Build the Q-Learning HTML section with Plotly heatmap."""
    if not q_table:
        return "<p>No Q-table data yet. Run some trades first.</p>"

    states  = sorted(q_table.keys())
    actions = ACTIONS

    # Build heatmap data
    z_rows  = []
    for action in actions:
        row = [round(q_table[s].get(action, 0.0), 4) for s in states]
        z_rows.append(row)

    z_json      = json.dumps(z_rows)
    states_json = json.dumps(states)
    actions_json = json.dumps(actions)

    alpha   = round(stats.get("alpha",   0.0), 6)
    epsilon = round(stats.get("epsilon", 0.0), 6)
    paused  = stats.get("paused", False)

    # Count best action per state
    action_counts = {a: 0 for a in ACTIONS}
    best_pairs    = []
    worst_pairs   = []

    for state, qvals in q_table.items():
        best_a = max(qvals, key=qvals.get)
        action_counts[best_a] += 1

    all_pairs = [
        (state, action, q_table[state][action])
        for state in q_table
        for action in q_table[state]
    ]
    all_pairs.sort(key=lambda x: x[2], reverse=True)
    best_pairs  = all_pairs[:3]
    worst_pairs = all_pairs[-3:]

    best_html  = "".join(f"<li><code>{s}|{a}</code> = {v:.4f}</li>" for s,a,v in best_pairs)
    worst_html = "".join(f"<li><code>{s}|{a}</code> = {v:.4f}</li>" for s,a,v in worst_pairs)
    count_html = "".join(
        f"<li><b>{a}</b>: {action_counts[a]} estados</li>" for a in ACTIONS
    )

    paused_badge = (
        '<span class="badge bg-danger">PAUSADO</span>'
        if paused else
        '<span class="badge bg-success">ACTIVO</span>'
    )

    return f"""
<div class="card mb-4">
  <div class="card-header d-flex justify-content-between align-items-center">
    <h5 class="mb-0">&#129504; Q-Learning Insights</h5>
    {paused_badge}
  </div>
  <div class="card-body">
    <div class="row mb-3">
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">Alpha (learning rate)</span>
          <span class="stat-value">{alpha}</span>
        </div>
      </div>
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">Epsilon (exploration)</span>
          <span class="stat-value">{epsilon}</span>
        </div>
      </div>
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">States discovered</span>
          <span class="stat-value">{len(q_table)} / 27</span>
        </div>
      </div>
    </div>

    <div id="qheatmap" style="height:350px;"></div>

    <div class="row mt-3">
      <div class="col-md-4">
        <h6>&#127881; Best state-actions</h6>
        <ul>{best_html}</ul>
      </div>
      <div class="col-md-4">
        <h6>&#128308; Worst state-actions</h6>
        <ul>{worst_html}</ul>
      </div>
      <div class="col-md-4">
        <h6>&#128200; Preferred action per state</h6>
        <ul>{count_html}</ul>
      </div>
    </div>
  </div>
</div>

<script>
(function() {{
  var z       = {z_json};
  var xLabels = {states_json};
  var yLabels = {actions_json};
  var trace = {{
    z:    z,
    x:    xLabels,
    y:    yLabels,
    type: 'heatmap',
    colorscale: 'RdYlGn',
    showscale: true,
  }};
  var layout = {{
    title:  'Q-Table heatmap (action x state)',
    margin: {{l:120, r:20, t:40, b:120}},
    xaxis:  {{tickangle: -45, tickfont: {{size: 10}}}},
  }};
  Plotly.newPlot('qheatmap', [trace], layout, {{responsive: true}});
}})();
</script>
"""


def generate(output_path: str = None):
    """Generate dashboard HTML file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts          = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"dashboard_{ts}.html")

    q_table = _load_json(QTABLE_PATH, {})
    stats   = _load_json(STATS_PATH,  {})

    ql_section = _build_qlearning_section(q_table, stats)

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bot3 Q-Learning - Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body          {{ background: #0d1117; color: #e6edf3; }}
    .card         {{ background: #161b22; border: 1px solid #30363d; }}
    .card-header  {{ background: #21262d; border-bottom: 1px solid #30363d; }}
    .stat-box     {{ display:flex; flex-direction:column; padding:12px; background:#0d1117; border-radius:6px; }}
    .stat-label   {{ font-size:.75rem; color:#8b949e; }}
    .stat-value   {{ font-size:1.4rem; font-weight:700; color:#58a6ff; }}
    h6            {{ color:#8b949e; }}
  </style>
</head>
<body>
<div class="container-fluid py-4">
  <h3 class="mb-1">Bot3 Q-Learning</h3>
  <p class="text-muted mb-4">Generated: {generated_at}</p>

  {ql_section}

</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Dashboard generated: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    path = generate()
    print(f"Dashboard: {path}")
''')

# =============================================================================
# test_integration.py  (patron bot2 - prueba end-to-end real con bot1)
# =============================================================================

write("test_integration.py", r'''
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
''')

# =============================================================================
# run_test_signal.py  (patron bot2/run_analysis.py - dry-run manual sin bot1)
# =============================================================================

write("run_test_signal.py", r'''
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
''')

# =============================================================================
# scripts/start_bot3.bat  (patron bot2: start_agente01.bat)
# =============================================================================

write("scripts/start_bot3.bat", r'''
@echo off
REM start_bot3.bat - Arranca Bot3 Q-Learning (patron bot2: start_agente01.bat)
title Bot3 Q-Learning

echo.
echo ============================================================
echo   Bot3 Q-Learning - Trading Signal Agent
echo ============================================================
echo.

REM Cargar variables de entorno desde .env si existe
if exist .env (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%a"=="" (
            set "line=%%a"
            if not "!line:~0,1!"=="#" set %%a=%%b
        )
    )
)

echo   DRY_RUN      : %DRY_RUN%
echo   Q-LEARNING   : %QLEARNING_ENABLED%
echo   PORT         : %PORT%
echo   WEBHOOK URL  : %BOT1_WEBHOOK_URL%
echo.
echo   Endpoints:
echo     POST http://localhost:8001/webhook/tv       TradingView alertas
echo     GET  http://localhost:8001/health           Estado del bot
echo     GET  http://localhost:8001/qlearning/status Agente Q-Learning
echo     GET  http://localhost:8001/pending          Decisiones pendientes
echo.
echo ============================================================
echo.

python bot3.py

pause
''')

# =============================================================================
# docs/ - remaining documentation files
# =============================================================================

write("docs/architecture.md", r'''
# Arquitectura de bot3-qlearning

Patron identico a bot2 (agente01). Capas de Research, Analysis, Decision y Sender.

## Diagrama de Componentes

```
+------------------------------------------------------------------+
|                          bot3.py                                 |
|              (FastAPI - puerto 8001 - event-driven)              |
|                                                                  |
|  Cada vez que TradingView dispara una alerta PineScript:         |
|                                                                  |
|  FASE 1: Validar envelope TV                                     |
|     a. Verificar X-Webhook-Secret (TV_WEBHOOK_SECRET)            |
|     b. Verificar IP si TV_ENFORCE_IP=true                        |
|     c. parse_tv_envelope() -> TVEnvelope validado                 |
|                                                                  |
|  FASE 2: Q-Learning Decision                                     |
|     a. state_encoder.encode_state() -> "regime|vol|momentum"      |
|     b. QLearningAgent.choose_action() (epsilon-greedy)           |
|     c. TVQLearningStrategy.decide()                              |
|        -> EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT             |
|                                                                  |
|  FASE 3: Envio a bot1 (patron identico a bot2)                   |
|     a. signal_formatter.build_payload() -> envelope bot1          |
|        strategy_id: "bot3_qlearning"                             |
|        source:      "bot3_qlearning_agent"                       |
|     b. webhook_client.send() -> POST /webhook/bot3                |
|        backoff: 5s -> 10s -> 15s (3 intentos)                      |
|        status="executed"  -> exito, track en pending_q_decisions  |
|        status="rejected"  -> log + Telegram *                    |
|        status="failed"    -> state/pending_signals.json           |
|                                                                  |
|  FASE 4: Persistencia (patron identico a bot2)                   |
|     a. _log_decision()       -> state/decision_log.jsonl          |
|     b. _write_event_report() -> logs/YYYY-MM-DD_HH-MM-SS.json    |
|     c. append_excel_rows()   -> logs/trade_log.xlsx               |
|     d. telegram_notifier.*() -> Telegram                          |
|                                                                  |
|  FASE 5: Hindsight Learning (POST /qlearning/update)             |
|     Cuando bot1 confirma cierre de posicion:                     |
|     a. compute_reward() -> formula: pnl_pct - slippage - penalty  |
|     b. agent.update() -> Bellman update Q(s,a)                    |
|     c. agent.decay_params() -> alpha y epsilon decaen             |
|     d. trainer.append_experience() -> replay_buffer.jsonl         |
|                                                                  |
+------------+-----------------------------------------------------+
             |
    +--------v----------------------------------------------+
    |                   SENDER LAYER                        |
    |              (patron identico a bot2)                 |
    |                                                       |
    |  sender/webhook_client.py                             |
    |  +- DRY_RUN=true  -> solo loguea, no envia             |
    |  +- POST a http://127.0.0.1:8000/webhook/bot3         |
    |  |   Header: X-Webhook-Secret (BOT1_WEBHOOK_SECRET)   |
    |  +- backoff: 5s -> 10s -> 15s (3 intentos)             |
    |  +- failed -> state/pending_signals.json               |
    |                                                       |
    |  sender/signal_formatter.py                           |
    |  +- build_payload() -> envelope compatible con bot1    |
    |  |   strategy_id: "bot3_qlearning"                    |
    |  |   source:      "bot3_qlearning_agent"              |
    |  +- build_no_signal_payload() -> informativo           |
    |                                                       |
    |  sender/telegram_notifier.py                          |
    |  +- signal_sent()     -> * ejecutado por bot1          |
    |  +- signal_rejected() -> * rechazado por bot1          |
    |  +- webhook_failed()  -> * fallo de red, en cola       |
    |  +- signal_skipped()  -> 🔍 Q-Learning descarto         |
    |  +- agent_paused()    -> 🛑 auto-pausa activada         |
    |  +- startup()         -> 🚀 bot3 arrancado              |
    +--------+----------------------------------------------+
             |
    +--------v----------------------------------------------+
    |                Q-LEARNING LAYER                       |
    |                                                       |
    |  core/qlearning_agent.py                              |
    |  +- Q-Table: 27 estados x 4 acciones                  |
    |  +- Epsilon-greedy: explora / explota                 |
    |  +- Bellman update al recibir reward                  |
    |  +- Auto-pause si win_rate < baseline * 0.7           |
    |  +- Persist: data/qlearning/q_table.json              |
    |                                                       |
    |  core/state_encoder.py                                |
    |  +- regime(3) x volatility(3) x momentum(3) = 27     |
    |                                                       |
    |  core/reward_calculator.py                            |
    |  +- r = pnl - slippage - duration_penalty + R_bonus  |
    |                                                       |
    |  manager/qlearning_trainer.py                         |
    |  +- replay_buffer.jsonl (historial de experiencias)   |
    |  +- Backups Q-table cada 6h (max 28)                  |
    +-------------------------------------------------------+

Estado en disco:
  state/decision_log.jsonl    - historial de todas las decisiones
  state/pending_signals.json  - senales en cola (retry automatico)
  data/qlearning/q_table.json - Q-table persistida
  logs/YYYY-MM-DD_HH-MM-SS.json - reporte por evento
  logs/trade_log.xlsx          - Excel acumulado
```
''')

write("docs/integration_bot1.md", r'''
# Integracion con Bot1

## Patron identico a bot2

bot3 se integra con bot1 exactamente igual que bot2:

### Registro en bot1

bot3 debe estar registrado en bot1 con `strategy_id="bot3_qlearning"`.
En bot1, en el BotRegistry o estrategias registradas, debe existir:
```
strategy_id: "bot3_qlearning"
source:      "bot3_qlearning_agent"
webhook_path: /webhook/bot3
```

### Formato del webhook

POST `http://127.0.0.1:8000/webhook/bot3`
Header: `X-Webhook-Secret: <BOT1_WEBHOOK_SECRET>`

```json
{
  "timestamp": "2026-05-03T14:30:00Z",
  "status": "pending",
  "signal": {
    "strategy_id": "bot3_qlearning",
    "symbol": "SPY",
    "action": "buy",
    "confidence": 0.75,
    "size": 0.10,
    "params": {
      "source":     "bot3_qlearning_agent",
      "ql_action":  "EXECUTE_FULL",
      "ql_state":   "trend_up|mid|bullish",
      "q_value":    0.1234,
      "regime":     "trend_up",
      "volatility": "mid",
      "momentum":   "bullish",
      "price":      520.50,
      "sl":         517.00,
      "tp":         527.00,
      "atr":        1.50
    }
  }
}
```

### Respuestas de bot1

| status              | Significado                              | Accion bot3         |
|---------------------|------------------------------------------|---------------------|
| `executed`          | bot1 ejecuto la orden en Alpaca          | Log + Telegram *   |
| `rejected`          | bot1 rechazo (bot pausado, etc.)         | Log + Telegram *   |
| `received_no_signal`| bot1 confirmo no_signal                  | Log                 |
| `failed`            | Fallo de red (no llego a bot1)           | pending_signals.json|
| `dry_run`           | DRY_RUN=true en bot3 (no se envio)       | Log local           |

### Retry automatico

Al arrancar bot3, `webhook_client.retry_pending()` reintenta todas las senales
en `state/pending_signals.json`. Identico al patron de bot2.

### Variables de entorno necesarias

```env
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=el_mismo_secreto_que_tiene_bot1
```
''')

write("docs/data_schemas.md", r'''
# Data Schemas

## `data/qlearning/q_table.json`

Q-table persistida en disco. Formato:

```json
{
  "trend_up|mid|bullish": {
    "EXECUTE_FULL": 0.12345,
    "EXECUTE_HALF": 0.05000,
    "SKIP":        -0.02000,
    "INVERT":      -0.08000
  },
  "range|low|neutral": {
    "EXECUTE_FULL": -0.03000,
    "EXECUTE_HALF":  0.01000,
    "SKIP":          0.07500,
    "INVERT":       -0.01000
  }
}
```

- **Clave outer:** estado codificado `"regime|volatility|momentum"`
- **Clave inner:** una de `EXECUTE_FULL | EXECUTE_HALF | SKIP | INVERT`
- **Valor:** Q-value (float, puede ser negativo)
- Inicializado en `0.0` de forma lazy cuando se visita el estado por primera vez

## `data/qlearning/qlearning_stats.json`

Hiperparametros actuales del agente:

```json
{
  "alpha":        0.09,
  "epsilon":      0.18,
  "gamma":        0.90,
  "paused":       false,
  "baseline_wr":  0.55,
  "last_updated": "2026-05-03T14:30:00"
}
```

## `data/qlearning/replay_buffer.jsonl`

Una experiencia por linea (JSONL):

```json
{"ts":"2026-05-03T14:35:22","s":"trend_up|mid|bullish","a":"EXECUTE_FULL","r":1.15,"s_next":"range|mid|neutral","done":false}
{"ts":"2026-05-03T16:12:00","s":"range|low|neutral","a":"SKIP","r":-0.05,"s_next":"range|low|neutral","done":true}
```

| Campo  | Tipo    | Descripcion                                              |
|--------|---------|----------------------------------------------------------|
| ts     | str     | timestamp UTC de cuando se cerro la posicion             |
| s      | str     | estado al entrar en la operacion                         |
| a      | str     | accion tomada por el agente                              |
| r      | float   | recompensa calculada por `compute_reward()`              |
| s_next | str     | estado del mercado al cerrar (o mismo estado si desconocido) |
| done   | bool    | true si el episodio termino sin s_next real              |

## `data/qlearning/backups/`

Backups automaticos de la Q-Table:

```
q_table_20260503_060000.json
q_table_20260503_120000.json
q_table_20260503_180000.json
...
```

Formato identico a `q_table.json`. Se mantienen los ultimos 28 (7 dias x 4/dia).

## `data/bot_status.json`

Estado de las estrategias registradas:

```json
{
  "strategy_tv_qlearning": {
    "status": "active",
    "paused_reason": null,
    "last_trade": "2026-05-03T14:35:22"
  }
}
```
''')

write("docs/environment_variables.md", r'''
# Variables de Entorno

Copia `.env.example` a `.env` y rellena los valores.

## Variables originales (heredadas de bot1)

| Variable              | Descripcion                                    | Ejemplo               |
|-----------------------|------------------------------------------------|-----------------------|
| ALPACA_API_KEY        | API key de Alpaca                              | PKxxx...              |
| ALPACA_SECRET_KEY     | Secret key de Alpaca                           | xxx...                |
| ALPACA_BASE_URL       | URL base del API de Alpaca                     | https://paper-api...  |
| WEBHOOK_SECRET        | Secreto para el webhook de Claude Routines     | changeme123           |
| TELEGRAM_BOT_TOKEN    | Token del bot de Telegram                      | 123456:AABBcc...      |
| TELEGRAM_CHAT_ID      | Chat ID de Telegram                            | -100123456789         |
| DRY_RUN               | true = no ejecuta ordenes reales               | true                  |
| PORT                  | Puerto del servidor FastAPI                    | 8001                  |

## Variables nuevas - TradingView Webhook

| Variable                  | Descripcion                                                  | Default  |
|---------------------------|--------------------------------------------------------------|----------|
| TV_WEBHOOK_SECRET         | Secreto para el header X-Webhook-Secret (distinto al otro)  | -        |
| TV_ALLOWED_IPS            | IPs de TradingView separadas por coma                        | (ver abajo) |
| TV_ENFORCE_IP_WHITELIST   | Validar IP de origen                                         | false    |

IPs oficiales de TradingView (2026): `52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7`

## Variables nuevas - Q-Learning

| Variable                      | Descripcion                                           | Default |
|-------------------------------|-------------------------------------------------------|---------|
| QLEARNING_ENABLED             | Activar el agente Q-Learning                          | true    |
| QLEARNING_ALPHA_INITIAL       | Learning rate inicial                                 | 0.10    |
| QLEARNING_ALPHA_MIN           | Learning rate minimo (floor del decay)                | 0.02    |
| QLEARNING_GAMMA               | Factor de descuento (horizonte temporal)              | 0.90    |
| QLEARNING_EPSILON_INITIAL     | Exploracion inicial (0=explotar, 1=explorar)          | 0.20    |
| QLEARNING_EPSILON_MIN         | Epsilon minimo (floor del decay)                      | 0.02    |
| QLEARNING_DECAY_PER_TRADE     | Multiplicador de decay por trade                      | 0.999   |
| QLEARNING_BACKUP_INTERVAL_HOURS | Cada cuantas horas crear backup de Q-Table          | 6       |
| QLEARNING_AUTO_PAUSE_WINDOW   | Numero de trades para evaluar degradacion             | 20      |
| QLEARNING_AUTO_PAUSE_WR_RATIO | Ratio de caida de win rate para auto-pausa            | 0.7     |
| QLEARNING_AUTO_PAUSE_DD_RATIO | Ratio de drawdown para auto-pausa                     | 1.5     |
''')

write("docs/end_to_end_flow.md", r'''
# End-to-End Flow - Bot3 Q-Learning

## Flujo completo: TradingView -> Q-Learning -> Alpaca

```
+-----------------+
|   TradingView   |
|   .pine alert   |
|  (EMA/ATR/RSI)  |
+--------+--------+
         |  POST /webhook/tv
         |  Header: X-Webhook-Secret
         |  Body: JSON envelope con regime, volatility, momentum
         v
+--------------------------------------------+
|               bot.py (FastAPI)             |
|                                            |
|  1. Validar secret (401 si falla)          |
|  2. Validar IP si TV_ENFORCE_IP=true (403) |
|  3. Parsear envelope (422 si invalido)     |
|  4. Si status != "pending" -> 200 silente  |
|                                            |
|  +--------------------------------------+  |
|  |       tv_signal_parser               |  |
|  |  parse_tv_envelope(body) -> TVEnvelope| |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |       state_encoder                  |  |
|  |  encode_state(params)                |  |
|  |  -> "trend_up|mid|bullish"           |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |       QLearningAgent (epsilon-greedy)|  |
|  |  choose_action(state)                |  |
|  |  -> EXECUTE_FULL / HALF / SKIP /     |  |
|  |     INVERT                           |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  +--------------v-----------------------+  |
|  |  TVQLearningStrategy.decide()        |  |
|  |  Aplica la accion:                   |  |
|  |   SKIP   -> return skipped (no trade)|  |
|  |   HALF   -> size *= 0.5              |  |
|  |   INVERT -> flip buy<->sell, *0.5    |  |
|  |   FULL   -> size sin cambio          |  |
|  +--------------+-----------------------+  |
|                 | (si execute=True)         |
|  +--------------v-----------------------+  |
|  |  OrderRouter (DRY_RUN o Alpaca live) |  |
|  |  Genera order_id                     |  |
|  +--------------+-----------------------+  |
|                 |                          |
|  pending_q_decisions[order_id] = {state, action, ts}
|                                            |
+--------------------------------------------+
         |
         |  Respuesta HTTP 200
         v
+---------------------------------------------+
|  {                                          |
|    "status": "executed" | "skipped_by_ql"  |
|    "order_id": "dry_SPY_...",               |
|    "ql_action": "EXECUTE_FULL",             |
|    "state": "trend_up|mid|bullish",         |
|    "q_value": 0.1234,                       |
|    ...                                      |
|  }                                          |
+---------------------------------------------+

**********************************************

## Flujo de aprendizaje: posicion cerrada

Cuando una posicion se cierra (TP, SL, o manual):

  POST /qlearning/update
  {order_id, pnl_pct, duration_min, account_drawdown_pct, r_multiple, next_state}
         |
         v
  compute_reward(trade_result)
         |
         v
  agent.update(s, a, r, s_next)
  Q(s,a) <- Q(s,a) + alpha * [r + gamma * max Q(s_next,.) - Q(s,a)]
         |
         v
  agent.decay_params()   # alpha *= 0.999, epsilon *= 0.999
         |
         v
  agent.check_degradation()  # auto-pausa si WR < baseline * 0.7
         |
         v
  trainer.append_experience() -> replay_buffer.jsonl
         |
         v
  agent.save() -> q_table.json + qlearning_stats.json

**********************************************

## Flujo nocturno (reentrenamiento offline)

  DailyRunner.run() (10:00 AM configurado via APScheduler)
         |
         v
  QLearningTrainer.train_from_replay(epochs=3)
         |  Lee replay_buffer.jsonl
         |  Shuffle + 3 passes de actualizaciones Bellman
         |  Decay adicional de alpha y epsilon
         v
  agent.save()
  trainer.backup_qtable()
         |
         v
  dashboard/generate_dashboard.py  (con seccion Q-Learning Insights)
''')

write("README.md", r'''
# Bot3 - Q-Learning Trading Bot

Trading bot que recibe alertas de **TradingView** (PineScript) y usa un agente
**Q-Learning** para decidir autonomamente si ejecutar, reducir, ignorar o invertir
cada senal. Aprende de cada operacion y mejora con el tiempo.

## Arquitectura

```
TradingView (.pine) --> POST /webhook/tv --> QLearningAgent --> Alpaca API
                                                   |
                                           Q-Table (persist)
                                           replay_buffer.jsonl
                                           auto-pausa por degradacion
```

## Canales de senal

| Canal            | Endpoint         | Descripcion                              |
|------------------|------------------|------------------------------------------|
| TradingView      | /webhook/tv      | Alertas EMA/ATR/RSI con Q-Learning       |

## Setup rapido

```bash
# 1. Crear estructura del proyecto (solo la primera vez)
python setup_project.py

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar entorno
copy .env.example .env
# editar .env con tus keys

# 4. Arrancar el bot
python bot.py

# 5. Verificar
curl http://localhost:8001/health

# 6. Tests
pytest tests/ -v
```

## Endpoints principales

| Metodo | Endpoint              | Descripcion                              |
|--------|-----------------------|------------------------------------------|
| GET    | /                     | Health check rapido                      |
| GET    | /health               | Estado detallado (mode, agent, pending)  |
| POST   | /webhook/tv           | Recibir alertas de TradingView           |
| GET    | /qlearning/status     | Alpha, epsilon, best/worst state-action  |
| GET    | /qlearning/qtable     | Q-table completa en JSON                 |
| POST   | /qlearning/update     | Aprendizaje cuando cierra una posicion   |
| POST   | /qlearning/pause      | Pausar agente manualmente                |
| POST   | /qlearning/resume     | Reanudar agente manualmente              |
| GET    | /pending              | Decisiones pendientes de cierre          |

## Testear manualmente (PowerShell)

```powershell
# Enviar senal de prueba
$env:TV_WEBHOOK_SECRET = "mi_secreto"
.\scripts\send_tv_signal.ps1

# O con curl
curl -X POST http://localhost:8001/webhook/tv `
  -H "Content-Type: application/json" `
  -H "X-Webhook-Secret: mi_secreto" `
  -d (Get-Content tests/fixtures/tv_envelope_buy.json -Raw)
```

## Estructura del proyecto

```
bot.py                              FastAPI entrypoint + todos los endpoints
core/
  qlearning_agent.py               Q-Table, epsilon-greedy, Bellman update
  state_encoder.py                 regime|volatility|momentum -> estado string
  reward_calculator.py             formula de recompensa post-trade
  tv_signal_parser.py              parser y validador del envelope TradingView
manager/
  qlearning_trainer.py             replay buffer, offline training, backups
strategies/
  strategy_tv_qlearning.py         logica de decision por accion Q-Learning
  pinescript/
    ema_atr_regime_v1.pine         estrategia PineScript para TradingView
dashboard/
  generate_dashboard.py            HTML con heatmap Q-Table y metricas
data/
  qlearning/
    q_table.json                   Q-Table persistida
    qlearning_stats.json           alpha, epsilon actuales
    replay_buffer.jsonl            historial de experiencias (s,a,r,s')
    backups/                       snapshots cada 6h (max 28)
utils/
  logger.py                        logger centralizado
scripts/
  send_tv_signal.ps1               plan B: enviar senal TV manualmente
  restore_qtable.ps1               restaurar Q-Table desde backup
  start_trading_stack.bat          arrancar el stack
docs/
  qlearning_strategy.md            descripcion completa del agente
  api_reference.md                 todos los endpoints documentados
  webhook_format.md                formato del envelope TradingView
  data_schemas.md                  schemas de q_table, replay_buffer, stats
  environment_variables.md         todas las variables de entorno
  end_to_end_flow.md               flujo completo de senal a trade a aprendizaje
tests/
  test_qlearning_agent.py          tests unitarios del agente Q-Learning
  fixtures/
    tv_envelope_buy.json           envelope de ejemplo para tests
```

## Variables de entorno importantes

| Variable             | Descripcion                       | Default |
|----------------------|-----------------------------------|---------|
| TV_WEBHOOK_SECRET    | Secreto para alertas TradingView  | -       |
| QLEARNING_ENABLED    | Activar agente Q-Learning         | true    |
| DRY_RUN              | No ejecutar ordenes reales        | true    |
| PORT                 | Puerto del servidor               | 8001    |

Ver `docs/environment_variables.md` para la lista completa.

## Documentacion

- [Estrategia Q-Learning](docs/qlearning_strategy.md)
- [API Reference](docs/api_reference.md)
- [Formato Webhook](docs/webhook_format.md)
- [Schemas de datos](docs/data_schemas.md)
- [Variables de entorno](docs/environment_variables.md)
- [Flujo end-to-end](docs/end_to_end_flow.md)
''')

# =============================================================================
# Summary
# =============================================================================

print("\n" + "=" * 60)
print("  Bot3 Q-Learning - Estructura creada exitosamente")
print("  (Homologada al patron de bot2 - Trading-agente-01)")
print("=" * 60)
print("\nEstructura creada:")
print("  bot3.py              FastAPI entrypoint (usa sender layer)")
print("  config.py            Configuracion centralizada (patron bot2)")
print("  excel_logger.py      Excel logging (patron bot2)")
print("  test_integration.py  Test end-to-end con bot1 (patron bot2)")
print("  run_test_signal.py   Dry-run sin enviar a bot1 (patron bot2)")
print("  sender/              webhook_client + signal_formatter + telegram")
print("  state/               decision_log.jsonl + pending_signals.json")
print("  logs/                Reportes JSON por evento + trade_log.xlsx")
print("  core/                Q-Learning engine (27 estados x 4 acciones)")
print("  manager/             Replay buffer + backups automaticos")
print("  strategies/          TVQLearningStrategy + PineScript")
print("  docs/                architecture + integration_bot1 + schemas")
print("\nFlujo de integracion:")
print("  TradingView -> POST /webhook/tv -> Q-Learning -> bot1 /webhook/bot3")
print("\nProximos pasos:")
print("  1. pip install -r requirements.txt")
print("  2. Copia .env.example a .env y completa las variables")
print("  3. python run_test_signal.py          (verificar Q-Learning local)")
print("  4. python test_integration.py         (verificar integracion bot1)")
print("  5. python bot3.py                     (arrancar el bot)")
print("  6. O usa: scripts/start_bot3.bat")
print("\nVariables criticas en .env:")
print("  BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3")
print("  BOT1_WEBHOOK_SECRET=<secreto_de_bot1>")
print("  TV_WEBHOOK_SECRET=<secreto_para_tradingview>")
print("  TELEGRAM_BOT_TOKEN=<token>")
print("  TELEGRAM_CHAT_ID=<chat_id>")
print("=" * 60)
