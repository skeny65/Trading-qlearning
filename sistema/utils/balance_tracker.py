"""
balance_tracker.py - Gestiona el balance USDT acumulado por carpeta.

Estado en: estrategias/estrategia_{id}/actividades/balance.json
Persiste entre reinicios del bot.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger("bot3.balance")


def _balance_path(folder_id: str) -> Path:
    return Path(config.strategy_actividades_dir(folder_id)) / "balance.json"


def get_balance(folder_id: str) -> float:
    """
    Retorna el balance USDT actual de la carpeta.
    Si no existe balance.json, usa balance_inicial_usdt del config.json.
    """
    path = _balance_path(folder_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return float(data.get("balance", 0))
        except Exception:
            pass
    # Primera vez: leer desde config.json de la carpeta
    try:
        from core.folder_config import load_folder_config
        cfg = load_folder_config(folder_id)
        return float(cfg.get("balance_inicial_usdt", 100.0))
    except Exception:
        return 100.0


def update_balance(folder_id: str, profit_usdt: float) -> tuple:
    """
    Aplica profit_usdt al balance y persiste el nuevo estado.
    Retorna (balance_antes, balance_despues).
    """
    balance_antes   = get_balance(folder_id)
    balance_despues = round(balance_antes + profit_usdt, 4)

    path = _balance_path(folder_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Leer estado existente para conservar campos como initial_balance y total_trades
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    data.setdefault("initial_balance", balance_antes)
    data["balance"]        = balance_despues
    data["updated_at"]     = datetime.now(timezone.utc).isoformat()
    data["total_trades"]   = data.get("total_trades", 0) + 1
    data["total_profit_usdt"] = round(data.get("total_profit_usdt", 0) + profit_usdt, 4)

    try:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.debug(
            f"[{folder_id}] Balance: {balance_antes:.4f} → {balance_despues:.4f} "
            f"({'+'if profit_usdt>=0 else ''}{profit_usdt:.4f} USDT)"
        )
    except Exception as e:
        logger.warning(f"[{folder_id}] No se pudo guardar balance.json: {e}")

    return balance_antes, balance_despues


def init_balance(folder_id: str, initial_usdt: float) -> None:
    """Inicializa (o reinicia) el balance de una carpeta."""
    path = _balance_path(folder_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "balance":           initial_usdt,
        "initial_balance":   initial_usdt,
        "updated_at":        datetime.now(timezone.utc).isoformat(),
        "total_trades":      0,
        "total_profit_usdt": 0.0,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"[{folder_id}] Balance inicializado en {initial_usdt:.2f} USDT")
