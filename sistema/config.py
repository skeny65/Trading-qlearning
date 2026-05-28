"""
config.py - Configuracion centralizada de bot3-qlearning.

Patron identico a bot2: todas las variables en un solo modulo.
Carga automaticamente .env si python-dotenv esta instalado.
"""
import os
import pathlib

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -- Rutas absolutas -----------------------------------------------------------
_SISTEMA_DIR    = pathlib.Path(__file__).parent          # .../Trading-qlearning/sistema
_ROOT_DIR       = _SISTEMA_DIR.parent                    # .../Trading-qlearning
ESTRATEGIAS_DIR = _ROOT_DIR / "estrategias"


def strategy_data_dir(strategy_id: str) -> str:
    """Retorna la ruta absoluta raiz de una estrategia (INSIGHTS.md y Excel aqui)."""
    return str(ESTRATEGIAS_DIR / f"estrategia_{strategy_id}")


def strategy_actividades_dir(strategy_id: str) -> str:
    """Retorna la ruta de archivos tecnicos (Q-tables, journals, events, backups)."""
    return str(ESTRATEGIAS_DIR / f"estrategia_{strategy_id}" / "actividades")

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

