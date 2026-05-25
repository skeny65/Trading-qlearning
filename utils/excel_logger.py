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
    # Llenadas al abrir como PENDING, actualizadas automaticamente al cerrar
    "result",      # PENDING → WIN o LOSS
    "pnl_pct",     # PENDING → "+1.45%" o "-0.29%"
    "pnl_notes",   # PENDING → "TP_HIT | 47min | R=2.34x"
    "learned_at",  # timestamp UTC del cierre
]

# Columnas que se agregan automaticamente si el Excel es antiguo
_NEW_COLUMNS = ["result", "pnl_pct", "pnl_notes", "learned_at"]

_COL_WIDTHS = {
    "timestamp_utc": 22, "event_id": 20, "strategy_id": 12, "mode": 8,
    "symbol": 10, "tv_action": 9, "ql_action": 14, "ql_state": 40,
    "q_value": 8, "regime": 10, "volatility": 10, "momentum": 10,
    "price": 8, "sl": 8, "tp": 8, "atr": 7,
    "execute": 8, "final_action": 12, "size": 7, "confidence": 11,
    "webhook_status": 14, "order_id": 36, "reason": 30,
    "epsilon": 8, "alpha": 7,
    "result": 10, "pnl_pct": 10, "pnl_notes": 30, "learned_at": 22,
}


def get_excel_path(strategy_id: str = "qlearning") -> str:
    return os.path.join("logs", strategy_id, "trade_log.xlsx")


def _format_header(ws) -> None:
    """Aplica formato a la fila de cabecera: fondo azul oscuro, texto blanco, columnas anchas."""
    try:
        from openpyxl.styles import Font, PatternFill, Alignment
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            if cell.value:
                cell.font      = header_font
                cell.fill      = header_fill
                cell.alignment = Alignment(horizontal="center")
                col_letter = cell.column_letter
                ws.column_dimensions[col_letter].width = _COL_WIDTHS.get(str(cell.value).lower(), 14)
        ws.freeze_panes = "A2"
    except Exception as e:
        logger.debug(f"Formato de cabecera no aplicado: {e}")


def _migrate_columns(ws) -> dict:
    """
    Detecta columnas nuevas (result, pnl_notes, learned_at) que no existen
    en el archivo y las agrega al final de la fila de cabecera con formato.

    Retorna el mapa {nombre_columna: indice_1based} de TODAS las columnas presentes.
    """
    try:
        from openpyxl.styles import Font, PatternFill, Alignment
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(bold=True, color="FFFFFF")
    except Exception:
        header_fill = None
        header_font = None

    # Mapa actual de columnas en el archivo
    header_row = next(ws.iter_rows(min_row=1, max_row=1))
    col_map    = {str(cell.value).lower(): cell.column for cell in header_row if cell.value}

    # Agregar columnas nuevas si faltan
    next_col = ws.max_column + 1
    for col_name in _NEW_COLUMNS:
        if col_name not in col_map:
            cell = ws.cell(row=1, column=next_col, value=col_name)
            if header_font:
                cell.font      = header_font
                cell.fill      = header_fill
                cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = _COL_WIDTHS.get(col_name, 14)
            col_map[col_name] = next_col
            logger.info(f"Columna '{col_name}' agregada al Excel existente (col {next_col})")
            next_col += 1

    return col_map


def update_excel_result(
    order_id:    str,
    result:      str,
    strategy_id: str = "qlearning",
    pnl_pct:     str = "",
    pnl_notes:   str = "",
) -> bool:
    """
    Busca la fila con order_id en el Excel y escribe result, pnl_pct, pnl_notes, learned_at.
    Sobreescribe aunque la fila diga PENDING (puesto al abrir).
    Si las columnas no existen (Excel antiguo), las migra automaticamente.
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl no instalado")
        return False

    excel_path = get_excel_path(strategy_id)
    if not os.path.exists(excel_path):
        return False

    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
    except PermissionError:
        logger.warning(f"Excel abierto [{strategy_id}] - cierra Excel para ver resultados automaticos")
        return False
    except Exception as e:
        logger.error(f"Error abriendo Excel [{strategy_id}]: {e}")
        return False

    # Migrar columnas si el archivo es antiguo, obtener mapa actualizado
    col_map     = _migrate_columns(ws)
    order_col   = col_map.get("order_id")
    result_col  = col_map.get("result")
    pnl_pct_col = col_map.get("pnl_pct")
    notes_col   = col_map.get("pnl_notes")
    learned_col = col_map.get("learned_at")

    if not all([order_col, result_col, notes_col, learned_col]):
        logger.error(f"Excel [{strategy_id}]: no se encontro columna order_id")
        return False

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    found  = False

    for row in ws.iter_rows(min_row=2):
        if str(row[order_col - 1].value or "").strip() == order_id:
            current = str(row[result_col - 1].value or "").strip()
            # Sobreescribir si esta vacio o en PENDING; respetar edicion manual del trader
            if current in ("", "PENDING"):
                row[result_col  - 1].value = result
                if pnl_pct_col:
                    row[pnl_pct_col - 1].value = pnl_pct
                row[notes_col   - 1].value = pnl_notes
                row[learned_col - 1].value = now_ts
                found = True
            break

    if found:
        try:
            wb.save(excel_path)
            logger.info(f"Excel [{strategy_id}] result={result} pnl={pnl_pct} order={order_id}")
        except PermissionError:
            logger.warning(f"Excel abierto [{strategy_id}] - no se pudo guardar resultado")
            return False
        except Exception as e:
            logger.error(f"Error guardando Excel [{strategy_id}]: {e}")
            return False

    return found


def append_excel_rows(rows: list, strategy_id: str = "qlearning") -> None:
    """
    Agrega filas a logs/{strategy_id}/trade_log.xlsx.
    Crea el archivo si no existe.
    Si el archivo es antiguo (sin columnas result/pnl_notes/learned_at), las migra.
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
            # Migrar columnas nuevas si el archivo es de una version anterior
            col_map = _migrate_columns(ws)
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"{strategy_id}_decisions"
            ws.append(COLUMNS)
            _format_header(ws)
            col_map = {name: idx + 1 for idx, name in enumerate(COLUMNS)}

        # Agregar filas nuevas usando el orden de columnas del archivo actual
        ordered_cols = sorted(col_map.items(), key=lambda x: x[1])
        col_names    = [name for name, _ in ordered_cols]
        for row_data in rows:
            ws.append([row_data.get(col, "") for col in col_names])

        wb.save(excel_path)
        logger.debug(f"Excel [{strategy_id}]: +{len(rows)} fila(s) -> {excel_path}")

    except PermissionError:
        logger.warning(f"Excel abierto en otro programa: {excel_path}")
    except Exception as e:
        logger.error(f"Error escribiendo Excel [{strategy_id}]: {e}")


def migrate_all_excel(strategies: list = None) -> None:
    """
    Migra manualmente los Excel de todas las estrategias para agregar
    las columnas result, pnl_notes, learned_at si no existen.

    Llamar una vez despues de actualizar bot3:
        from utils.excel_logger import migrate_all_excel
        migrate_all_excel()

    O desde PowerShell:
        python -c "from utils.excel_logger import migrate_all_excel; migrate_all_excel()"
    """
    try:
        import openpyxl
    except ImportError:
        print("ERROR: pip install openpyxl")
        return

    if strategies is None:
        strategies = ["apuesta", "qlearning", "tanque"]

    for strategy_id in strategies:
        excel_path = get_excel_path(strategy_id)
        if not os.path.exists(excel_path):
            print(f"[{strategy_id}] Sin Excel todavia: {excel_path}")
            continue
        try:
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            col_map = _migrate_columns(ws)
            wb.save(excel_path)
            added = [c for c in _NEW_COLUMNS if c in col_map]
            print(f"[{strategy_id}] OK - columnas presentes: {added}")
        except PermissionError:
            print(f"[{strategy_id}] ERROR: Excel abierto. Cierra Excel y vuelve a correr.")
        except Exception as e:
            print(f"[{strategy_id}] ERROR: {e}")
