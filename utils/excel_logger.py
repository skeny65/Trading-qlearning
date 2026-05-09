"""
excel_logger.py - Registro Excel por estrategia.

Cada estrategia tiene su propio archivo:
  logs/apuesta/trade_log.xlsx
  logs/qlearning/trade_log.xlsx
  logs/tanque/trade_log.xlsx

Una fila por senal recibida.
Si el archivo esta abierto en Excel, advierte sin crashear el bot.
"""
import logging
import os

logger = logging.getLogger("bot3.excel")

COLUMNS = [
    "timestamp_utc",
    "event_id",
    "strategy_id",
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


def get_excel_path(strategy_id: str = "qlearning") -> str:
    return os.path.join("logs", strategy_id, "trade_log.xlsx")


def append_excel_rows(rows: list, strategy_id: str = "qlearning") -> None:
    """
    Acumula filas en logs/{strategy_id}/trade_log.xlsx.
    Crea el archivo si no existe. Agrega filas si ya existe.
    """
    if not rows:
        return

    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl no instalado - Excel logging desactivado")
        return

    excel_path = get_excel_path(strategy_id)
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)

    try:
        if os.path.exists(excel_path):
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"{strategy_id}_decisions"
            ws.append(COLUMNS)

        for row in rows:
            ws.append([row.get(col, "") for col in COLUMNS])

        wb.save(excel_path)
        logger.debug(f"Excel [{strategy_id}]: +{len(rows)} fila(s) -> {excel_path}")

    except PermissionError:
        logger.warning(f"Excel abierto en otro programa: {excel_path}")
    except Exception as e:
        logger.error(f"Error escribiendo Excel [{strategy_id}]: {e}")
