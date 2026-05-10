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
from datetime import datetime, timezone

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
    # Revision manual del trader (el bot deja estas columnas vacias)
    "result",      # Llena tu: WIN / LOSS  (dejar vacio = no revisado)
    "pnl_notes",   # Notas opcionales: "+2.3%", "SL justo antes de revertir", etc.
    "learned_at",  # Lo llena learn_from_excel.py automaticamente al procesar
]


def get_excel_path(strategy_id: str = "qlearning") -> str:
    return os.path.join("logs", strategy_id, "trade_log.xlsx")


def _format_header(ws) -> None:
    """Aplica formato a la fila de cabecera: fondo azul oscuro, texto blanco, anchos utiles."""
    try:
        from openpyxl.styles import Font, PatternFill, Alignment
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
        # Anchos utiles
        col_widths = {
            "timestamp_utc": 22, "event_id": 20, "strategy_id": 12, "mode": 8,
            "symbol": 10, "tv_action": 9, "ql_action": 14, "ql_state": 40,
            "q_value": 8, "regime": 10, "volatility": 10, "momentum": 10,
            "price": 8, "sl": 8, "tp": 8, "atr": 7,
            "execute": 8, "final_action": 12, "size": 7, "confidence": 11,
            "webhook_status": 14, "order_id": 36, "reason": 30,
            "epsilon": 8, "alpha": 7,
            "result": 8, "pnl_notes": 28, "learned_at": 22,
        }
        for col_idx, col_name in enumerate(COLUMNS, 1):
            col_letter = ws.cell(1, col_idx).column_letter
            ws.column_dimensions[col_letter].width = col_widths.get(col_name, 14)
    except Exception as e:
        logger.debug(f"Formato de cabecera no aplicado: {e}")


def update_excel_result(
    order_id:    str,
    result:      str,   # "WIN" o "LOSS"
    strategy_id: str   = "qlearning",
    pnl_notes:   str   = "",
) -> bool:
    """
    Busca la fila con order_id dado en el Excel de la estrategia y escribe:
      - result    -> "WIN" o "LOSS"
      - pnl_notes -> descripcion del cierre (pnl%, TP_HIT/SL_HIT, etc.)
      - learned_at -> timestamp actual

    Retorna True si encontro y actualizo la fila, False si no la encontro.
    Llamado automaticamente por PricePoller cuando detecta TP o SL.
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl no instalado - update_excel_result desactivado")
        return False

    excel_path = get_excel_path(strategy_id)
    if not os.path.exists(excel_path):
        return False

    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
    except PermissionError:
        logger.warning(f"Excel abierto en otro programa [{strategy_id}] - resultado no actualizado para {order_id}")
        return False
    except Exception as e:
        logger.error(f"Error abriendo Excel [{strategy_id}]: {e}")
        return False

    # Construir mapa columna -> indice (1-based)
    header_row = next(ws.iter_rows(min_row=1, max_row=1))
    col_map    = {str(cell.value).lower(): cell.column for cell in header_row if cell.value}

    order_col   = col_map.get("order_id")
    result_col  = col_map.get("result")
    notes_col   = col_map.get("pnl_notes")
    learned_col = col_map.get("learned_at")

    if not all([order_col, result_col, notes_col, learned_col]):
        logger.warning(f"Excel [{strategy_id}] no tiene columnas esperadas - regenerar con bot3 actual")
        return False

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    found  = False

    for row in ws.iter_rows(min_row=2):
        cell_order = row[order_col - 1]
        if str(cell_order.value or "").strip() == order_id:
            # Solo actualizar si aun no tiene resultado (no sobreescribir edicion manual)
            if not row[result_col - 1].value:
                row[result_col  - 1].value = result
                row[notes_col   - 1].value = pnl_notes
                row[learned_col - 1].value = now_ts
                found = True
            break

    if found:
        try:
            wb.save(excel_path)
            logger.info(f"Excel [{strategy_id}] actualizado: order={order_id} result={result} notes={pnl_notes}")
        except PermissionError:
            logger.warning(f"Excel abierto en otro programa [{strategy_id}] - cierra Excel para ver resultados")
            return False
        except Exception as e:
            logger.error(f"Error guardando Excel [{strategy_id}]: {e}")
            return False

    return found


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
            _format_header(ws)

        for row in rows:
            ws.append([row.get(col, "") for col in COLUMNS])

        wb.save(excel_path)
        logger.debug(f"Excel [{strategy_id}]: +{len(rows)} fila(s) -> {excel_path}")

    except PermissionError:
        logger.warning(f"Excel abierto en otro programa: {excel_path}")
    except Exception as e:
        logger.error(f"Error escribiendo Excel [{strategy_id}]: {e}")
