"""
learn_from_excel.py - Aprendizaje desde revision manual en Excel.

Flujo:
  1. TradingView manda alerta -> bot3 decide y escribe fila en Excel
  2. El trader revisa el resultado y escribe WIN o LOSS en la columna 'result'
  3. Este script lee esas filas y llama a bot3 para que el agente aprenda
  4. El script marca 'learned_at' para no procesar la fila dos veces

Uso:
  python scripts/learn_from_excel.py                # todas las estrategias
  python scripts/learn_from_excel.py qlearning      # solo una estrategia
  python scripts/learn_from_excel.py --dry-run      # muestra filas, no aprende

Requisito:
  - bot3 corriendo en localhost:8001
  - openpyxl instalado (pip install openpyxl)

Columnas necesarias en el Excel:
  - result     -> el trader escribe: WIN o LOSS
  - ql_state   -> estado Q-Learning (lo escribe el bot automaticamente)
  - ql_action  -> accion tomada (lo escribe el bot automaticamente)
  - order_id   -> ID de la orden (lo escribe el bot automaticamente)
  - learned_at -> lo llena este script (no editar manualmente)
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BOT3_URL   = "http://localhost:8001"
STRATEGIES = ["apuesta", "qlearning", "tanque"]

# Reward que se pasa al agente segun el resultado manual
WIN_PNL   = +1.0   # trade ganador
LOSS_PNL  = -1.0   # trade perdedor


def get_excel_path(strategy_id: str) -> Path:
    return Path("logs") / strategy_id / "trade_log.xlsx"


def process_strategy(strategy_id: str, dry_run: bool = False) -> int:
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl no instalado. Ejecuta: pip install openpyxl")
        return 0

    excel_path = get_excel_path(strategy_id)
    if not excel_path.exists():
        print(f"[{strategy_id}] Sin Excel todavia: {excel_path}")
        return 0

    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
    except PermissionError:
        print(f"[{strategy_id}] Excel abierto en otro programa. Cierra Excel y vuelve a correr.")
        return 0
    except Exception as e:
        print(f"[{strategy_id}] Error abriendo Excel: {e}")
        return 0

    # Construir mapa columna -> indice (1-based)
    header_row  = next(ws.iter_rows(min_row=1, max_row=1))
    col_map     = {str(cell.value).lower(): cell.column for cell in header_row if cell.value}

    required = {"result", "ql_state", "ql_action", "order_id", "learned_at", "execute"}
    missing  = required - col_map.keys()
    if missing:
        print(
            f"[{strategy_id}] Columnas faltantes en Excel: {missing}\n"
            "  El Excel debe ser generado por bot3 actual. Borra trade_log.xlsx y reinicia bot3."
        )
        return 0

    now_ts    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    processed = 0
    skipped   = 0

    for row in ws.iter_rows(min_row=2):
        # Obtener celdas relevantes
        def cell(col_name):
            idx = col_map.get(col_name)
            return row[idx - 1] if idx else None

        result_cell   = cell("result")
        learned_cell  = cell("learned_at")
        execute_cell  = cell("execute")
        state_cell    = cell("ql_state")
        action_cell   = cell("ql_action")
        order_cell    = cell("order_id")
        event_cell    = cell("event_id")
        symbol_cell   = cell("symbol")

        result  = str(result_cell.value  or "").strip().upper()
        learned = str(learned_cell.value or "").strip()
        execute = str(execute_cell.value or "").strip()

        # Solo procesar filas con resultado marcado y sin procesar
        if result not in ("WIN", "LOSS"):
            continue
        if learned:
            skipped += 1
            continue
        if execute.upper() not in ("TRUE", "1", "YES"):
            # SKIP no tiene resultado a aprender; marcar para no revisitar
            learned_cell.value = f"SKIPPED_{now_ts}"
            continue

        state   = str(state_cell.value  or "").strip()
        action  = str(action_cell.value or "").strip()
        order   = str(order_cell.value  or "").strip()
        symbol  = str(symbol_cell.value or "").strip() if symbol_cell else "?"

        if not state or not action:
            print(f"  [{strategy_id}] Fila sin state/action - omitida (order={order})")
            continue

        pnl_pct = WIN_PNL if result == "WIN" else LOSS_PNL

        print(f"[{strategy_id}] {symbol} | {result} | state={state} | action={action}")

        if not dry_run:
            ok = _call_update(strategy_id, order, pnl_pct, state, action)
            if ok:
                learned_cell.value = now_ts
                processed += 1
                print(f"  -> Aprendizaje aplicado ({pnl_pct:+.1f}). INSIGHTS.md actualizado.")
            else:
                print(f"  -> ERROR: no se pudo actualizar. Verifica que bot3 este corriendo.")
        else:
            processed += 1
            print(f"  -> DRY_RUN: se enviaria pnl={pnl_pct:+.1f}")

    if not dry_run:
        if processed > 0:
            try:
                wb.save(excel_path)
                print(f"\n[{strategy_id}] {processed} fila(s) procesadas. Excel guardado.")
            except PermissionError:
                print(f"\n[{strategy_id}] ERROR: Excel abierto. Cierra Excel y vuelve a correr.")
        else:
            print(f"[{strategy_id}] Sin filas nuevas con WIN/LOSS para procesar.")
    else:
        print(f"[{strategy_id}] DRY_RUN: {processed} fila(s) listas para procesar.")

    if skipped:
        print(f"[{strategy_id}] {skipped} fila(s) ya procesadas anteriormente (learned_at lleno).")

    return processed


def _call_update(
    strategy_id: str,
    order_id:    str,
    pnl_pct:     float,
    state:       str,
    action:      str,
) -> bool:
    """Llama a POST /api/strategy/{id}/update con state y action directos."""
    url  = f"{BOT3_URL}/api/strategy/{strategy_id}/update"
    body = json.dumps({
        "order_id":    order_id,
        "pnl_pct":     pnl_pct,
        "duration_min": 0.0,
        "state":       state,    # evita depender de pending_q_decisions en memoria
        "action":      action,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body_text[:200]}")
        return False
    except Exception as e:
        print(f"  Error de conexion: {e}")
        return False


def _check_bot3_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{BOT3_URL}/", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Procesa resultados WIN/LOSS del Excel y dispara aprendizaje Q-Learning."
    )
    parser.add_argument(
        "strategy", nargs="?",
        help="Estrategia a procesar (apuesta | qlearning | tanque). Omitir = todas."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra las filas a procesar sin enviar nada a bot3."
    )
    parser.add_argument(
        "--url", default=BOT3_URL,
        help=f"URL de bot3 (default: {BOT3_URL})"
    )
    args = parser.parse_args()

    if args.url != BOT3_URL:
        BOT3_URL = args.url

    if not args.dry_run and not _check_bot3_alive():
        print(f"ERROR: bot3 no responde en {BOT3_URL}")
        print("Inicia bot3 primero o usa --dry-run para solo ver que se procesaria.")
        sys.exit(1)

    targets = [args.strategy] if args.strategy else STRATEGIES
    total   = 0

    print(f"{'DRY-RUN: ' if args.dry_run else ''}Procesando estrategias: {targets}\n")

    for sid in targets:
        total += process_strategy(sid, dry_run=args.dry_run)

    print(f"\nTotal: {total} fila(s) {'listas' if args.dry_run else 'procesadas'}.")
