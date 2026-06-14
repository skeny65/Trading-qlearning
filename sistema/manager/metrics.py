"""
metrics.py - Metricas por carpeta: winrate, pnl, duracion, desglose.

Lee ejecuciones.jsonl (o trade_log.xlsx como fallback) de cada carpeta
y calcula estadisticas descriptivas sobre los resultados.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger("bot3.metrics")


def _read_ejecuciones(folder_id: str) -> list:
    """Lee el JSONL de ejecuciones de la carpeta."""
    path = Path(config.strategy_actividades_dir(folder_id)) / "ejecuciones.jsonl"
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"[{folder_id}] Error leyendo ejecuciones.jsonl: {e}")
    return entries


def _read_excel(folder_id: str) -> list:
    """Lee el Excel como fallback si ejecuciones.jsonl no tiene datos."""
    try:
        import openpyxl
    except ImportError:
        return []

    excel_path = os.path.join(config.strategy_data_dir(folder_id), "trade_log.xlsx")
    if not os.path.exists(excel_path):
        return []

    try:
        wb   = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws   = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).lower() for h in rows[0]]
        result  = []
        for row in rows[1:]:
            result.append(dict(zip(headers, row)))
        return result
    except Exception as e:
        logger.warning(f"[{folder_id}] Error leyendo Excel: {e}")
        return []


def _compute(entries: list, folder_id: str) -> dict:
    """Calcula metricas a partir de entradas de ejecuciones/excel."""
    closes = [
        e for e in entries
        if str(e.get("tipo", e.get("signal_type", ""))).lower() == "close"
        and str(e.get("resultado", e.get("result", ""))).upper() in ("WIN", "LOSS")
    ]

    total  = len(closes)
    wins   = sum(1 for e in closes if str(e.get("resultado", e.get("result", ""))).upper() == "WIN")
    losses = total - wins

    def _pnl(e):
        raw = e.get("pnl_pct", "")
        if raw is None or raw == "":
            return None
        try:
            return float(str(raw).replace("%", "").replace("+", ""))
        except Exception:
            return None

    pnls = [p for p in (_pnl(e) for e in closes) if p is not None]

    pnl_acumulado = round(sum(pnls), 4) if pnls else 0.0
    pnl_medio     = round(sum(pnls) / len(pnls), 4) if pnls else 0.0
    mejor_trade   = round(max(pnls), 4) if pnls else 0.0
    peor_trade    = round(min(pnls), 4) if pnls else 0.0

    winrate = round(wins / total * 100, 2) if total else 0.0

    # Duracion media
    duraciones = []
    for e in closes:
        d = e.get("duration_min")
        if d is not None:
            try:
                duraciones.append(float(d))
            except Exception:
                pass
    duracion_media = round(sum(duraciones) / len(duraciones), 1) if duraciones else 0.0

    # Desglose por symbol
    by_symbol: dict = {}
    for e in closes:
        sym = str(e.get("symbol", "?"))
        res = str(e.get("resultado", e.get("result", ""))).upper()
        if sym not in by_symbol:
            by_symbol[sym] = {"win": 0, "loss": 0, "total": 0}
        if res == "WIN":
            by_symbol[sym]["win"] += 1
        elif res == "LOSS":
            by_symbol[sym]["loss"] += 1
        by_symbol[sym]["total"] += 1

    # Desglose por close_reason
    by_reason: dict = {}
    for e in closes:
        reason = str(e.get("close_reason", e.get("pnl_notes", "?"))).split("|")[0].strip()
        res    = str(e.get("resultado", e.get("result", ""))).upper()
        if reason not in by_reason:
            by_reason[reason] = {"win": 0, "loss": 0}
        if res == "WIN":
            by_reason[reason]["win"] += 1
        elif res == "LOSS":
            by_reason[reason]["loss"] += 1

    return {
        "folder_id":      folder_id,
        "total_trades":   total,
        "wins":           wins,
        "losses":         losses,
        "winrate_pct":    winrate,
        "pnl_acumulado":  pnl_acumulado,
        "pnl_medio":      pnl_medio,
        "mejor_trade":    mejor_trade,
        "peor_trade":     peor_trade,
        "duracion_media_min": duracion_media,
        "por_symbol":     by_symbol,
        "por_razon":      by_reason,
        "updated_at":     datetime.now(timezone.utc).isoformat(),
    }


def metrics_for_folder(folder_id: str) -> dict:
    """Calcula y retorna metricas para una carpeta."""
    entries = _read_ejecuciones(folder_id)
    if not entries:
        entries = _read_excel(folder_id)
    return _compute(entries, folder_id)


def metrics_all() -> dict:
    """Consolida metricas de todas las carpetas."""
    result = {}
    total_global = wins_global = losses_global = 0
    for i in range(1, 11):
        fid     = str(i)
        m       = metrics_for_folder(fid)
        result[fid] = m
        total_global  += m["total_trades"]
        wins_global   += m["wins"]
        losses_global += m["losses"]

    wr_global = round(wins_global / total_global * 100, 2) if total_global else 0.0
    return {
        "carpetas":          result,
        "consolidado": {
            "total_trades": total_global,
            "wins":         wins_global,
            "losses":       losses_global,
            "winrate_pct":  wr_global,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_insights_md(folder_id: str) -> str:
    """Genera el contenido markdown de INSIGHTS.md para una carpeta."""
    m    = metrics_for_folder(folder_id)
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# INSIGHTS — Carpeta {folder_id}",
        f"> Generado: {now}",
        "",
        "## Resumen",
        f"| Metrica | Valor |",
        f"|---------|-------|",
        f"| Total trades | {m['total_trades']} |",
        f"| Wins | {m['wins']} |",
        f"| Losses | {m['losses']} |",
        f"| Winrate | {m['winrate_pct']:.2f}% |",
        f"| PnL acumulado | {m['pnl_acumulado']:+.4f}% |",
        f"| PnL medio | {m['pnl_medio']:+.4f}% |",
        f"| Mejor trade | {m['mejor_trade']:+.4f}% |",
        f"| Peor trade | {m['peor_trade']:+.4f}% |",
        f"| Duracion media | {m['duracion_media_min']:.1f} min |",
        "",
    ]

    if m["por_symbol"]:
        lines += ["## Por simbolo", "| Symbol | Wins | Losses | Total |", "|--------|------|--------|-------|"]
        for sym, d in m["por_symbol"].items():
            lines.append(f"| {sym} | {d['win']} | {d['loss']} | {d['total']} |")
        lines.append("")

    if m["por_razon"]:
        lines += ["## Por razon de cierre", "| Razon | Wins | Losses |", "|-------|------|--------|"]
        for reason, d in m["por_razon"].items():
            lines.append(f"| {reason} | {d['win']} | {d['loss']} |")
        lines.append("")

    return "\n".join(lines)


def save_all_insights() -> None:
    """Escribe INSIGHTS.md en cada carpeta con metricas actualizadas."""
    for i in range(1, 11):
        fid     = str(i)
        content = generate_insights_md(fid)
        path    = Path(config.strategy_data_dir(fid)) / "INSIGHTS.md"
        try:
            path.write_text(content, encoding="utf-8")
            logger.info(f"[{fid}] INSIGHTS.md actualizado")
        except Exception as e:
            logger.warning(f"[{fid}] Error escribiendo INSIGHTS.md: {e}")
