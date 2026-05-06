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
