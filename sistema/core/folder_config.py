"""
folder_config.py - Carga y validacion de la configuracion por carpeta.
"""
import json
import logging
from pathlib import Path

import config

logger = logging.getLogger("bot3.folder_config")

_REQUIRED_FIELDS = ["id", "emisor", "enabled", "modo_cierre", "sizing"]
_DEFAULTS = {
    "coloca_sltp_en_binance": False,
    "account_type": "futures_usdt",
    "symbols_permitidos": [],
    "notas": "",
}

_VALID_MODOS = {"dos_senales", "sltp_en_binance", "una_senal_poller", "bot_grid", "bot_manager", "trailing_stop"}


def load_folder_config(folder_id: str) -> dict:
    """
    Lee estrategias/estrategia_{id}/config.json y valida campos obligatorios.
    Si falta el archivo o hay error, retorna config con enabled=false.
    """
    path = Path(config.strategy_data_dir(folder_id)) / "config.json"
    if not path.exists():
        logger.error(f"[{folder_id}] config.json no encontrado: {path}")
        return {"id": folder_id, "enabled": False, "error": "config.json no encontrado"}

    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        logger.error(f"[{folder_id}] Error leyendo config.json: {e}")
        return {"id": folder_id, "enabled": False, "error": str(e)}

    # Aplicar defaults para campos opcionales
    for k, v in _DEFAULTS.items():
        cfg.setdefault(k, v)

    # Validar campos obligatorios
    missing = [f for f in _REQUIRED_FIELDS if f not in cfg]
    if missing:
        logger.error(f"[{folder_id}] config.json faltan campos: {missing}")
        cfg["enabled"] = False
        cfg["error"]   = f"faltan campos: {missing}"
        return cfg

    # Validar modo_cierre
    if cfg["modo_cierre"] not in _VALID_MODOS:
        logger.error(f"[{folder_id}] modo_cierre invalido: {cfg['modo_cierre']}")
        cfg["enabled"] = False
        cfg["error"]   = f"modo_cierre invalido: {cfg['modo_cierre']}"

    # Validar sizing
    sizing = cfg.get("sizing", {})
    if sizing.get("tipo") == "margen_fijo_usdt" and not sizing.get("margen_usdt"):
        logger.warning(f"[{folder_id}] sizing.margen_usdt no definido, usando default de .env")
        sizing["margen_usdt"] = config.BINANCE_DEFAULT_MARGIN_USDT

    if not sizing.get("leverage"):
        sizing["leverage"] = config.BINANCE_DEFAULT_LEVERAGE

    return cfg


def all_enabled_folders() -> list:
    """Retorna lista de IDs de carpetas habilitadas (enabled=true)."""
    enabled = []
    for i in range(1, 11):
        cfg = load_folder_config(str(i))
        if cfg.get("enabled", False):
            enabled.append(str(i))
    return enabled


def all_folder_configs() -> dict:
    """Retorna dict {id: config} para todas las carpetas 1-10."""
    return {str(i): load_folder_config(str(i)) for i in range(1, 11)}
