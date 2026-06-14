"""
config.py - Configuracion centralizada del bot_ejecutor.
"""
import os
import pathlib

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -- Rutas absolutas -----------------------------------------------------------
_SISTEMA_DIR    = pathlib.Path(__file__).parent
_ROOT_DIR       = _SISTEMA_DIR.parent
ESTRATEGIAS_DIR = _ROOT_DIR / "estrategias"


def strategy_data_dir(strategy_id: str) -> str:
    """Raiz de la carpeta de una estrategia (config.json, INSIGHTS.md, trade_log.xlsx)."""
    return str(ESTRATEGIAS_DIR / f"estrategia_{strategy_id}")


def strategy_actividades_dir(strategy_id: str) -> str:
    """Subcarpeta de archivos tecnicos (senales, ejecuciones, backups, eventos)."""
    return str(ESTRATEGIAS_DIR / f"estrategia_{strategy_id}" / "actividades")


# -- Servidor ------------------------------------------------------------------
PORT    = int(os.getenv("PORT", "8001"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# -- TradingView webhook -------------------------------------------------------
TV_WEBHOOK_SECRET = os.getenv("TV_WEBHOOK_SECRET", "")
TV_ALLOWED_IPS    = [
    ip.strip()
    for ip in os.getenv("TV_ALLOWED_IPS", "").split(",")
    if ip.strip()
]
TV_ENFORCE_IP     = os.getenv("TV_ENFORCE_IP_WHITELIST", "false").lower() == "true"

# -- Binance Futuros -----------------------------------------------------------
BINANCE_DEFAULT_LEVERAGE    = int(os.getenv("BINANCE_DEFAULT_LEVERAGE",    "10"))
BINANCE_DEFAULT_MARGIN_USDT = float(os.getenv("BINANCE_DEFAULT_MARGIN_USDT", "5.0"))
BINANCE_MAX_MARGIN_PCT      = float(os.getenv("BINANCE_MAX_MARGIN_PCT",     "0.95"))

# -- Telegram ------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
