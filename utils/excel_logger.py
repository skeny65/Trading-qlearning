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
