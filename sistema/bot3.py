"""
bot3.py - bot_ejecutor: router de ejecucion puro.

Recibe señales de TradingView, bot_grid, bot_manager u otros emisores.
Interpreta la señal segun el formato configurado para cada carpeta.
Ejecuta open/close en Binance Futuros USDT-M.
Registra todo en los logs de la carpeta.
Sin Q-Learning. Sin decision propia. Si llega open, abre; si llega close, cierra.

Endpoints:
    GET  /                          health check rapido
    GET  /health                    estado detallado
    POST /webhook/{id}              senal para carpeta 1-10
    GET  /api/folders               lista carpetas con config y posiciones
    GET  /api/folder/{id}/status    config + posiciones abiertas
    GET  /api/folder/{id}/metrics   metricas de la carpeta
    GET  /api/metrics               metricas consolidadas
    GET  /pending                   posiciones monitoreadas por el poller
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel

from core.folder_config  import load_folder_config, all_folder_configs
from core.adapters       import get_adapter
from core                import binance_executor
from manager.price_poller    import PricePoller
from manager.bot_grid_poller import BotGridPoller
from utils.excel_logger  import append_excel_row, update_excel_result
from utils               import balance_tracker
from utils.logger        import setup_logger
from sender              import telegram_notifier

logger = setup_logger("bot3")

# -- globals -------------------------------------------------------------------

# {(folder_id, symbol): {order_id, side, open_time, entry_price, sl, tp, sizing_cfg}}
open_positions: dict = {}

# Para el price poller (carpetas con modo_cierre != dos_senales)
# {order_id: {symbol, side, entry_price, sl, tp, open_time, folder_id}}
pending_poller: dict = {}

poller: Optional[PricePoller] = None
bot_grid_poller: Optional[BotGridPoller] = None

# --- Estado adicional para protocolo v2.0 /signal ---
processed_signals: set = set()    # deduplicacion por signal_id
paused_sources:    set = set()    # fuentes pausadas (PAUSE/RESUME)
position_id_index: dict = {}      # position_id → (folder_id, symbol)

_MAX_DEDUP_SIZE = 5_000

# Mapa: source emisor → folder_id (protocolo v2.0)
_SOURCE_FOLDER: dict = {
    "bot_grid":    "9",
    "bot_manager": "10",
}

_FOLDER_IDS = [str(i) for i in range(1, 11)]


# -- helpers de persistencia ---------------------------------------------------

def _senales_path(folder_id: str) -> Path:
    return Path(config.strategy_actividades_dir(folder_id)) / "senales_recibidas.jsonl"


def _ejecuciones_path(folder_id: str) -> Path:
    return Path(config.strategy_actividades_dir(folder_id)) / "ejecuciones.jsonl"


def _log_senal(folder_id: str, signal_interna: dict, raw_body: dict) -> None:
    """Registra TODA señal recibida, incluso de carpetas disabled o señales invalidas."""
    path = _senales_path(folder_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "folder_id":  folder_id,
        "signal":     signal_interna,
        "raw":        raw_body,
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[{folder_id}] No se pudo escribir senales_recibidas: {e}")


def _log_ejecucion(folder_id: str, entry: dict) -> None:
    path = _ejecuciones_path(folder_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[{folder_id}] No se pudo escribir ejecuciones: {e}")


def _write_event(folder_id: str, report: dict) -> None:
    events_dir = Path(config.strategy_actividades_dir(folder_id)) / "eventos"
    events_dir.mkdir(parents=True, exist_ok=True)
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    fpath = events_dir / f"{ts}.json"
    try:
        fpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[{folder_id}] No se pudo escribir evento: {e}")


# -- lifespan ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poller, bot_grid_poller

    # Crear directorios necesarios por carpeta
    for fid in _FOLDER_IDS:
        act = Path(config.strategy_actividades_dir(fid))
        act.mkdir(parents=True, exist_ok=True)
        (act / "eventos").mkdir(parents=True, exist_ok=True)
        (act / "backups").mkdir(parents=True, exist_ok=True)
        Path(config.strategy_data_dir(fid)).mkdir(parents=True, exist_ok=True)

    logger.info(f"Arrancando bot_ejecutor - DRY_RUN={config.DRY_RUN} PORT={config.PORT}")

    # Cargar configs y loguear estado de carpetas
    configs = all_folder_configs()
    enabled = [fid for fid, cfg in configs.items() if cfg.get("enabled")]
    logger.info(f"Carpetas habilitadas: {enabled}")

    # Arrancar price poller (monitorea carpetas con modo_cierre != dos_senales)
    poller = PricePoller(pending_poller, configs, open_positions)
    poller.start()

    # Arrancar bot_grid poller (monitorea carpetas con modo_cierre == bot_grid)
    grid_configs = {fid: cfg for fid, cfg in configs.items() if cfg.get("modo_cierre") == "bot_grid"}
    if grid_configs:
        bot_grid_poller = BotGridPoller(open_positions, grid_configs)
        bot_grid_poller.start()

    telegram_notifier.startup(config.DRY_RUN, config.PORT)

    yield

    if poller:
        poller.stop()
    if bot_grid_poller:
        bot_grid_poller.stop()


app = FastAPI(
    title="bot_ejecutor",
    version="2.0.0",
    lifespan=lifespan,
)


# -- helpers de seguridad ------------------------------------------------------

def _check_ip(request: Request):
    if not config.TV_ENFORCE_IP:
        return
    client_ip = request.client.host if request.client else ""
    if client_ip not in config.TV_ALLOWED_IPS:
        raise HTTPException(status_code=403, detail=f"IP no permitida: {client_ip}")


def _check_secret(secret: Optional[str], query_secret: Optional[str] = None):
    if not config.TV_WEBHOOK_SECRET:
        logger.warning("TV_WEBHOOK_SECRET no configurado - aceptando todo (INSEGURO)")
        return
    if secret == config.TV_WEBHOOK_SECRET or query_secret == config.TV_WEBHOOK_SECRET:
        return
    raise HTTPException(status_code=401, detail="Webhook secret invalido")


# -- routes --------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status":  "ok",
        "bot":     "bot_ejecutor",
        "version": "2.0.0",
        "dry_run": config.DRY_RUN,
    }


def _bot_grid_status() -> dict:
    """Lee el heartbeat.json que Bot_Grid escribe en cada ciclo de health (cada 30s)."""
    hb_path = Path(r"C:\Users\kenyb\Desktop\BOT_EJECUTOR\Bot_Grid\logs\heartbeat.json")
    try:
        if not hb_path.exists():
            return {"status": "offline", "detail": "heartbeat.json no encontrado"}
        data       = json.loads(hb_path.read_text(encoding="utf-8"))
        updated_at = data.get("updated_at", "")
        try:
            age_sec = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(updated_at)).total_seconds()
            data["age_seconds"] = int(age_sec)
            if age_sec > 5 * 60:   # sin actividad más de 5 minutos
                data["status"] = "stale"
        except Exception:
            pass
        return data
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _bot_manager_status() -> dict:
    """Lee el heartbeat.json que Bot_Manager escribe en cada scan."""
    hb_path = Path(r"C:\Users\kenyb\Desktop\BOT_EJECUTOR\Bot_Manager\logs\heartbeat.json")
    try:
        if not hb_path.exists():
            return {"status": "offline", "detail": "heartbeat.json no encontrado"}
        data       = json.loads(hb_path.read_text(encoding="utf-8"))
        updated_at = data.get("updated_at", "")
        try:
            age_sec = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(updated_at)).total_seconds()
            data["age_seconds"] = int(age_sec)
            if age_sec > 120 * 60:   # sin actividad más de 2 horas
                data["status"] = "stale"
        except Exception:
            pass
        return data
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/health")
def health():
    configs = all_folder_configs()
    enabled   = [fid for fid, cfg in configs.items() if cfg.get("enabled")]
    dry_local = [fid for fid, cfg in configs.items() if not cfg.get("binance_live", False) and not config.DRY_RUN]
    return {
        "status":                 "ok",
        "dry_run_global":         config.DRY_RUN,
        "carpetas_activas":       enabled,
        "carpetas_dry_run_local": dry_local,
        "posiciones_abiertas":    len(open_positions),
        "poller_monitored":       len(pending_poller),
        "price_poller":           poller.get_status() if poller else None,
        "bot_grid_poller":        bot_grid_poller.get_status() if bot_grid_poller else None,
        "bot_grid":               _bot_grid_status(),
        "bot_manager":            _bot_manager_status(),
        "timestamp":              datetime.now(timezone.utc).isoformat(),
    }


@app.get("/pending")
def get_pending():
    return {"pending": pending_poller, "count": len(pending_poller)}


# =============================================================================
# ENDPOINT /signal — Protocolo unificado v2.0 (BOT_MANAGER + BOT_GRID)
# =============================================================================

_VALID_ACTIONS_V2 = {"OPEN", "CLOSE", "ADJUST", "PAUSE", "RESUME"}
_VALID_SOURCES_V2 = {"bot_grid", "bot_manager"}


@app.post("/signal")
async def signal_v2(
    request:          Request,
    background_tasks: BackgroundTasks,
    x_secret: Optional[str] = Header(None),
):
    """
    Endpoint unificado para BOT_MANAGER y BOT_GRID (protocolo v2.0).
    Acciones: OPEN / CLOSE / ADJUST / PAUSE / RESUME.
    Deduplicacion por signal_id. Routing automatico por source.
    """
    query_secret = request.query_params.get("secret")
    _check_secret(x_secret, query_secret)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")

    # Validar campos obligatorios del protocolo v2.0
    required = {"signal_id", "source", "timestamp", "action", "symbol"}
    missing  = required - body.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"missing_field: {', '.join(sorted(missing))}")

    action    = str(body.get("action",    "")).upper()
    source    = str(body.get("source",    "")).lower()
    signal_id = str(body.get("signal_id", ""))
    symbol    = str(body.get("symbol",    "")).upper()

    if action not in _VALID_ACTIONS_V2:
        raise HTTPException(status_code=422, detail=f"invalid action: {action}")
    if source not in _VALID_SOURCES_V2:
        raise HTTPException(status_code=422, detail=f"invalid source: {source}")

    # Timestamp fresco (< 5 min)
    try:
        ts  = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > 300:
            raise HTTPException(status_code=422, detail=f"stale signal: {age:.0f}s old")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="invalid timestamp format")

    # Deduplicacion por signal_id
    if signal_id in processed_signals:
        return {"status": "duplicate", "signal_id": signal_id}
    processed_signals.add(signal_id)
    if len(processed_signals) > _MAX_DEDUP_SIZE:
        processed_signals.clear()

    # Resolver carpeta por source
    folder_id = _SOURCE_FOLDER.get(source)
    if not folder_id:
        raise HTTPException(status_code=422, detail=f"source sin carpeta asignada: {source}")

    cfg = load_folder_config(folder_id)
    if not cfg.get("enabled", False):
        return {"status": "accepted", "signal_id": signal_id, "skipped": "folder_disabled"}

    queued_at = datetime.now(timezone.utc).isoformat()

    # PAUSE / RESUME — control de flujo por source
    if action == "PAUSE":
        paused_sources.add(source)
        logger.info(f"[/signal] {source} PAUSE — nuevas entradas bloqueadas")
        return {"status": "accepted", "signal_id": signal_id, "paused": source, "queued_at": queued_at}
    if action == "RESUME":
        paused_sources.discard(source)
        logger.info(f"[/signal] {source} RESUME — entradas reactivadas")
        return {"status": "accepted", "signal_id": signal_id, "resumed": source, "queued_at": queued_at}

    # Symbol permitido
    permitidos = cfg.get("symbols_permitidos", [])
    if permitidos and symbol not in permitidos:
        return {"status": "accepted", "signal_id": signal_id, "skipped": f"symbol {symbol} no permitido"}

    event_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    # ---- OPEN ----
    if action == "OPEN":
        if source in paused_sources:
            return {"status": "accepted", "signal_id": signal_id, "skipped": f"{source} pausado"}
        if not body.get("side"):
            raise HTTPException(status_code=422, detail="missing_field: side (required for OPEN)")
        if body.get("sl") is None:
            raise HTTPException(status_code=422, detail="missing_field: sl (required for OPEN)")

        if (folder_id, symbol) in open_positions:
            return {"status": "accepted", "signal_id": signal_id, "skipped": f"posicion ya abierta para {symbol}"}

        # Override sizing si el emisor lo especifica
        sizing_cfg = dict(cfg["sizing"])
        if body.get("size_usdt"):
            sizing_cfg["margen_usdt"] = float(body["size_usdt"])
        elif body.get("size_pct") and not config.DRY_RUN:
            try:
                bal = binance_executor.get_usdt_balance()
                sizing_cfg["margen_usdt"] = round(bal * float(body["size_pct"]) / 100, 2)
            except Exception:
                pass

        signal_internal = {
            "tipo":        "open",
            "symbol":      symbol,
            "side":        str(body["side"]).lower(),
            "price":       float(body.get("price", 0)),
            "sl":          float(body["sl"]),
            "tp":          float(body["tp"]) if body.get("tp") is not None else None,
            "position_id": body.get("position_id"),
            "signal_id":   signal_id,
        }
        cfg_eff = {**cfg, "sizing": sizing_cfg}
        _log_senal(folder_id, signal_internal, body)

        pos_id = body.get("position_id")
        if pos_id:
            position_id_index[pos_id] = (folder_id, symbol)

        background_tasks.add_task(_execute_open, folder_id, cfg_eff, signal_internal, event_id)

    # ---- CLOSE ----
    elif action == "CLOSE":
        pos_id = body.get("position_id")
        if pos_id and pos_id in position_id_index:
            folder_id, symbol = position_id_index.pop(pos_id)

        signal_internal = {
            "tipo":         "close",
            "symbol":       symbol,
            "price":        float(body.get("price", 0)),
            "close_reason": "CLOSE_SIGNAL_V2",
            "pnl_pct":      body.get("pnl_pct"),
        }
        open_pos = open_positions.pop((folder_id, symbol), None)
        _log_senal(folder_id, signal_internal, body)
        background_tasks.add_task(_execute_close, folder_id, cfg, signal_internal, open_pos or {}, event_id)

    # ---- ADJUST ----
    elif action == "ADJUST":
        pos_id = body.get("position_id")
        if not pos_id:
            raise HTTPException(status_code=422, detail="missing_field: position_id (required for ADJUST)")
        if pos_id in position_id_index:
            folder_id, symbol = position_id_index[pos_id]

        new_sl = float(body["sl"]) if body.get("sl") is not None else None
        new_tp = float(body["tp"]) if body.get("tp") is not None else None

        logger.info(f"[/signal|{folder_id}|{symbol}] ADJUST pos_id={pos_id} sl={new_sl} tp={new_tp}")
        background_tasks.add_task(_execute_adjust, folder_id, symbol, new_sl, new_tp, event_id)

    return {
        "status":        "accepted",
        "signal_id":     signal_id,
        "queued_at":     queued_at,
        "executor_mode": "dry-run" if config.DRY_RUN else "real",
    }


# =============================================================================
# WEBHOOK PRINCIPAL
# =============================================================================

def _execute_open(folder_id: str, cfg: dict, signal: dict, event_id: str):
    """Background task: abre posicion en Binance y registra."""
    symbol     = signal["symbol"]
    side       = signal["side"]
    price      = signal["price"]
    sl         = signal.get("sl")
    tp         = signal.get("tp")
    sizing_cfg = dict(cfg["sizing"])
    # dry_run global O por carpeta (config.json "dry_run": true)
    dry_run    = config.DRY_RUN or not cfg.get("binance_live", False)
    mode_label = "DRY_RUN" if dry_run else "LIVE"
    coloca_sltp = cfg.get("coloca_sltp_en_binance", False)

    # Sizing dinámico: usa % del balance disponible en Binance
    if sizing_cfg.get("tipo") == "pct_balance":
        import math
        pct = float(sizing_cfg.get("pct", 95)) / 100
        try:
            bal = binance_executor.get_usdt_balance()
            # floor a 2 decimales para no superar el límite BINANCE_MAX_MARGIN_PCT
            margen = math.floor(bal * pct * 100) / 100
            sizing_cfg["margen_usdt"] = margen
            logger.info(
                f"[{folder_id}|{symbol}] pct_balance: balance={bal:.2f} USDT "
                f"-> margen={margen:.2f} USDT ({pct*100:.0f}%)"
            )
        except Exception as e:
            logger.error(f"[{folder_id}|{symbol}] pct_balance: no se pudo obtener balance: {e}")
            return

    # ── Sizing por riesgo fijo (riesgo_fijo_pct) ──────────────────────────────
    if sizing_cfg.get("tipo") == "riesgo_fijo_pct":
        from core.risk import calcular_qty_por_riesgo, MAX_RISK_PCT

        sl_distance = signal.get("sl_distance")
        risk_pct    = signal.get("risk_pct") or float(sizing_cfg.get("risk_pct", 5.0))
        leverage    = int(sizing_cfg.get("leverage", 25))

        if not sl_distance or sl_distance <= 0:
            logger.error(
                f"[{folder_id}|{symbol}] riesgo_fijo_pct: sl_distance ausente o invalida "
                f"({sl_distance}) — la alerta debe incluir 'sl_distance' en params"
            )
            return

        if dry_run:
            try:
                bal = binance_executor.get_usdt_balance()
            except Exception:
                bal = 0.0
            riesgo_usdt = bal * min(risk_pct, MAX_RISK_PCT) / 100
            qty_sim     = riesgo_usdt / sl_distance if sl_distance else 0
            order_id       = f"dry_{symbol}_{event_id}"
            binance_status = "dry_run"
            detail         = (
                f"simulado qty~{qty_sim:.4f} "
                f"riesgo={riesgo_usdt:.2f} USDT ({min(risk_pct, MAX_RISK_PCT)}%) "
                f"sl_dist={sl_distance:.4f} lev={leverage}x"
            )
            sizing_cfg["margen_usdt"] = round(riesgo_usdt, 2)
            sizing_cfg["leverage"]    = leverage
            logger.info(f"[{folder_id}|{symbol}] DRY_RUN risk-sizing: {detail}")
        else:
            try:
                bal   = binance_executor.get_usdt_balance()
                filt  = binance_executor._get_filters(symbol)
                qty, riesgo_usdt = calcular_qty_por_riesgo(
                    bal, risk_pct, sl_distance, price, filt
                )
                logger.info(
                    f"[{folder_id}|{symbol}] risk-sizing: balance={bal:.2f} "
                    f"risk={min(risk_pct, MAX_RISK_PCT)}% sl_dist={sl_distance:.4f} "
                    f"-> qty={qty} riesgo={riesgo_usdt:.2f} USDT"
                )
            except ValueError as e:
                logger.error(f"[{folder_id}|{symbol}] calcular_qty error: {e}")
                return
            except Exception as e:
                logger.error(f"[{folder_id}|{symbol}] risk-sizing error inesperado: {e}")
                return

            result         = binance_executor.open_position_by_risk(symbol, side, qty, sl, tp, leverage)
            binance_status = result["status"]
            order_id       = result.get("order_id") or event_id
            detail         = result.get("detail", "")

            # Margen informativo para Excel (notional / leverage)
            notional = qty * price if price else 0
            sizing_cfg["margen_usdt"] = round(notional / leverage, 2)
            sizing_cfg["leverage"]    = leverage

            if binance_status == "ok":
                logger.info(f"[{folder_id}|{symbol}] Binance open OK: {side} {detail} order={order_id}")
                telegram_notifier.signal_sent(symbol, side, riesgo_usdt, "OPEN OK", detail, False)
            else:
                logger.error(f"[{folder_id}|{symbol}] Binance error: {detail}")
                telegram_notifier.webhook_failed(symbol, detail)
                return

    # ── Sizing estándar (margen_fijo_usdt / pct_balance) ──────────────────────
    else:
        binance_sl = sl if coloca_sltp else None
        binance_tp = tp if coloca_sltp else None

        if dry_run:
            order_id = f"dry_{symbol}_{event_id}"
            dry_tag  = "(carpeta)" if not cfg.get("binance_live", False) and not config.DRY_RUN else "(global)"
            logger.info(f"[{folder_id}|{symbol}] DRY_RUN {dry_tag} open: {side} price={price}")
            binance_status = "dry_run"
            detail         = f"simulado qty=~{(sizing_cfg.get('margen_usdt',0)*sizing_cfg.get('leverage',1)/price if price else 0):.4f}"
        else:
            result         = binance_executor.open_position(symbol, side, price, sizing_cfg, binance_sl, binance_tp)
            binance_status = result["status"]
            order_id       = result.get("order_id") or event_id
            detail         = result.get("detail", "")

            if binance_status == "ok":
                logger.info(f"[{folder_id}|{symbol}] Binance open OK: {side} {detail} order={order_id}")
                telegram_notifier.signal_sent(symbol, side, sizing_cfg.get("margen_usdt", 0), "OPEN OK", detail, False)

                # Trailing stop: intentar en Binance; si falla, el poller lo maneja internamente
                ts_cfg = cfg.get("trailing_stop", {})
                if ts_cfg.get("enabled"):
                    risk_pct = float(ts_cfg.get("risk_pct", 10.0))
                    pct_b    = float(sizing_cfg.get("pct", 95)) / 100
                    lev      = float(sizing_cfg.get("leverage", 25))
                    cb_rate  = risk_pct / (pct_b * lev)
                    sizing_cfg["_trailing_callback"] = cb_rate

                    qty_ts = result.get("qty", 0)
                    ts_res = binance_executor.place_trailing_stop(symbol, side, cb_rate, qty_ts)
                    if ts_res["status"] == "ok":
                        logger.info(
                            f"[{folder_id}|{symbol}] Trailing stop Binance activo: "
                            f"callback={ts_res['callback_rate']}% qty={qty_ts}"
                        )
                    else:
                        logger.warning(
                            f"[{folder_id}|{symbol}] Trailing stop Binance no soportado — "
                            f"poller interno activo con callback={cb_rate:.3f}%"
                        )

            elif binance_status == "skip":
                logger.warning(f"[{folder_id}|{symbol}] Binance skip: {detail}")
                telegram_notifier.signal_rejected(symbol, detail)
                return
            else:
                logger.error(f"[{folder_id}|{symbol}] Binance error: {detail}")
                telegram_notifier.webhook_failed(symbol, detail)
                return

    open_time = datetime.now(timezone.utc).isoformat()

    # Registrar apertura en memoria
    open_positions[(folder_id, symbol)] = {
        "order_id":    order_id,
        "side":        side,
        "open_time":   open_time,
        "entry_price": price,
        "sl":          sl,
        "tp":          tp,
        "sizing_cfg":  sizing_cfg,
        "binance_status": binance_status,
    }

    # Si el modo de cierre requiere poller, agregar a pending_poller
    _modo_cierre = cfg.get("modo_cierre", "")
    _needs_poller = _modo_cierre not in ("dos_senales",) and (
        (sl and tp) or _modo_cierre == "trailing_stop"
    )
    if _needs_poller:
        pending_poller[order_id] = {
            "folder_id":    folder_id,
            "symbol":       symbol,
            "side":         side,
            "entry_price":  price,
            "sl":           sl,
            "tp":           tp,
            "open_time":    open_time,
            "margen_usdt":  sizing_cfg.get("margen_usdt", 0),
            "leverage":     sizing_cfg.get("leverage", 1),
            "callback_rate": sizing_cfg.get("_trailing_callback", 0),
            "peak_price":   price,
        }

    # Excel — fila PENDING
    bal_antes = balance_tracker.get_balance(folder_id)
    excel_row = {
        "timestamp_utc":  open_time,
        "event_id":       event_id,
        "id_carpeta":     folder_id,
        "emisor":         cfg.get("emisor", ""),
        "mode":           mode_label,
        "symbol":         symbol,
        "side":           side,
        "price":          price,
        "sl":             sl or "",
        "tp":             tp or "",
        "margen_usdt":    sizing_cfg.get("margen_usdt", ""),
        "leverage":       sizing_cfg.get("leverage", ""),
        "order_id":       order_id,
        "binance_status": binance_status,
        "balance_antes":  round(bal_antes, 4),
    }
    append_excel_row(excel_row, folder_id)

    ejecucion = {**excel_row, "signal": signal}
    _log_ejecucion(folder_id, ejecucion)
    _write_event(folder_id, ejecucion)


def _execute_close(folder_id: str, cfg: dict, signal: dict, open_pos: dict, event_id: str):
    """Background task: cierra posicion en Binance y actualiza Excel."""
    symbol       = signal["symbol"]
    close_price  = signal["price"]
    pnl_pct      = signal.get("pnl_pct")
    close_reason = signal.get("close_reason", "señal_close")
    dry_run      = config.DRY_RUN or not cfg.get("binance_live", False)
    mode_label   = "DRY_RUN" if dry_run else "LIVE"

    # Calcular pnl si no vino en el payload
    if not pnl_pct and open_pos.get("entry_price") and close_price:
        entry = float(open_pos["entry_price"])
        if open_pos["side"] == "buy":
            pnl_pct = round((close_price - entry) / entry * 100, 4)
        else:
            pnl_pct = round((entry - close_price) / entry * 100, 4)

    if dry_run:
        logger.info(f"[{folder_id}|{symbol}] DRY_RUN close: pnl={pnl_pct:+.4f}% reason={close_reason}")
    else:
        result = binance_executor.close_position(symbol)
        logger.info(
            f"[{folder_id}|{symbol}] Binance close: status={result['status']} "
            f"pnl={(pnl_pct if pnl_pct is not None else 0):+.4f}% reason={close_reason}"
        )

    # Duracion
    try:
        open_dt      = datetime.fromisoformat(open_pos["open_time"].replace("Z", "+00:00"))
        duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60
    except Exception:
        duration_min = 0.0

    resultado = "WIN" if (pnl_pct or 0) > 0 else "LOSS"
    pnl_notes = f"{close_reason.upper()} | {duration_min:.0f}min"

    # Calcular profit en USDT real
    sizing_cfg  = open_pos.get("sizing_cfg", {})
    margen_usdt = float(sizing_cfg.get("margen_usdt", 0) or 0)
    leverage    = float(sizing_cfg.get("leverage",    1) or 1)
    profit_usdt = round(margen_usdt * leverage * (pnl_pct or 0) / 100, 4)

    # Actualizar balance de la carpeta
    bal_antes, bal_despues = balance_tracker.update_balance(folder_id, profit_usdt)

    matched_order_id = open_pos.get("order_id", event_id)

    update_excel_result(
        order_id        = matched_order_id,
        result          = resultado,
        strategy_id     = folder_id,
        pnl_pct         = f"{pnl_pct:+.4f}%" if pnl_pct is not None else "",
        pnl_notes       = pnl_notes,
        precio_salida   = close_price,
        duracion_min    = duration_min,
        profit_usdt     = profit_usdt,
        balance_antes   = bal_antes,
        balance_despues = bal_despues,
    )

    # Limpiar de pending_poller si estaba ahi
    pending_poller.pop(matched_order_id, None)

    ejecucion = {
        "ts":           datetime.now(timezone.utc).isoformat(),
        "event_id":     event_id,
        "id_carpeta":   folder_id,
        "tipo":         "close",
        "symbol":       symbol,
        "close_price":  close_price,
        "pnl_pct":      pnl_pct,
        "close_reason": close_reason,
        "duration_min": duration_min,
        "resultado":    resultado,
        "order_id":     matched_order_id,
        "mode":         mode_label,
    }
    _log_ejecucion(folder_id, ejecucion)
    _write_event(folder_id, ejecucion)

    telegram_notifier.signal_sent(
        symbol, "close", 0, resultado, f"{pnl_pct:+.4f}%" if pnl_pct is not None else "", False
    )
    logger.info(f"[{folder_id}|{symbol}] {resultado} pnl={(pnl_pct if pnl_pct is not None else 0):+.4f}% dur={duration_min:.0f}min")


def _execute_adjust(folder_id: str, symbol: str, new_sl: Optional[float], new_tp: Optional[float], event_id: str):
    """Background task: actualiza SL/TP de posicion existente (protocolo v2.0 ADJUST)."""
    pos     = open_positions.get((folder_id, symbol))
    cfg     = load_folder_config(folder_id)
    dry_run = config.DRY_RUN or not cfg.get("binance_live", False)

    if dry_run:
        logger.info(f"[{folder_id}|{symbol}] DRY_RUN ADJUST sl={new_sl} tp={new_tp}")
        if pos:
            if new_sl is not None:
                pos["sl"] = new_sl
            if new_tp is not None:
                pos["tp"] = new_tp
        return

    binance_executor.cancel_open_orders(symbol)  # solo en LIVE

    if not pos:
        logger.warning(f"[{folder_id}|{symbol}] ADJUST: sin posicion en memoria para recolocar ordenes")
        return

    side    = pos["side"]
    cl_side = "SELL" if side == "buy" else "BUY"

    from core.binance_executor import get_client, _get_filters, _round_down
    from decimal import Decimal

    try:
        filt   = _get_filters(symbol)
        client = get_client()
    except Exception as e:
        logger.error(f"[{folder_id}|{symbol}] ADJUST setup error: {e}")
        return

    if new_sl and new_sl > 0:
        try:
            from binance.exceptions import BinanceAPIException
            sl_dec = _round_down(Decimal(str(new_sl)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="STOP_MARKET",
                stopPrice=str(sl_dec), closePosition=True, workingType="MARK_PRICE",
            )
            pos["sl"] = new_sl
            logger.info(f"[{folder_id}|{symbol}] ADJUST SL → {sl_dec}")
        except Exception as e:
            logger.error(f"[{folder_id}|{symbol}] ADJUST SL error: {e}")

    if new_tp and new_tp > 0:
        try:
            from binance.exceptions import BinanceAPIException
            tp_dec = _round_down(Decimal(str(new_tp)), filt["tick"])
            client.futures_create_order(
                symbol=symbol, side=cl_side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(tp_dec), closePosition=True, workingType="MARK_PRICE",
            )
            pos["tp"] = new_tp
            logger.info(f"[{folder_id}|{symbol}] ADJUST TP → {tp_dec}")
        except Exception as e:
            logger.error(f"[{folder_id}|{symbol}] ADJUST TP error: {e}")


@app.post("/webhook/{folder_id}")
async def webhook(
    folder_id: str,
    request:   Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Recibe señales de cualquier emisor y las ejecuta en Binance.
    Flujo: validar → parsear → loguear señal → ejecutar open/close → responder.
    """
    _check_ip(request)
    query_secret = request.query_params.get("secret")
    _check_secret(x_webhook_secret, query_secret)

    # Validar que la carpeta existe (1-10)
    if folder_id not in _FOLDER_IDS:
        raise HTTPException(status_code=404, detail=f"Carpeta '{folder_id}' no existe (1-10)")

    try:
        raw  = await request.body()
        body = json.loads(raw.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")

    event_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    # Cargar config de la carpeta
    cfg = load_folder_config(folder_id)

    # Parsear señal (siempre, incluso si disabled — para auditoria)
    adapter = get_adapter(cfg.get("emisor", "generico"))
    try:
        signal = adapter.parse(body, folder_id)
    except Exception as e:
        _log_senal(folder_id, {"error": str(e), "raw": body}, body)
        raise HTTPException(status_code=422, detail=f"Payload invalido: {e}")

    # Loguear señal cruda SIEMPRE
    _log_senal(folder_id, signal, body)

    # Si la carpeta esta disabled, responder sin ejecutar
    if not cfg.get("enabled", False):
        logger.info(f"[{folder_id}] Carpeta deshabilitada — senal recibida pero no ejecutada")
        return {"ok": True, "skipped": "disabled", "folder_id": folder_id}

    # Ignorar señales que no requieren accion (ej. status != pending en TradingView)
    if signal.get("tipo") == "ignorar":
        logger.info(f"[{folder_id}] Señal ignorada: {signal.get('motivo', '')}")
        return {"ok": True, "skipped": signal.get("motivo", "ignorar")}

    # Validar symbol permitido
    permitidos = cfg.get("symbols_permitidos", [])
    if permitidos and signal.get("symbol") not in permitidos:
        logger.warning(f"[{folder_id}] Symbol {signal.get('symbol')} no permitido — skip")
        return {"ok": True, "skipped": f"symbol {signal.get('symbol')} no permitido"}

    tipo   = signal.get("tipo")
    symbol = signal.get("symbol")

    if tipo == "open":
        # Evitar doble apertura del mismo symbol en la misma carpeta
        if (folder_id, symbol) in open_positions:
            logger.warning(f"[{folder_id}|{symbol}] Ya hay posicion abierta — skip duplicado")
            return {"ok": True, "skipped": f"posicion ya abierta para {symbol}"}

        background_tasks.add_task(_execute_open, folder_id, cfg, signal, event_id)

    elif tipo == "close":
        open_pos = open_positions.pop((folder_id, symbol), None)
        logger.info(
            f"[{folder_id}|{symbol}] CLOSE: open_found={open_pos is not None} "
            f"reason={signal.get('close_reason', '')}"
        )
        background_tasks.add_task(_execute_close, folder_id, cfg, signal, open_pos or {}, event_id)

    else:
        logger.warning(f"[{folder_id}] tipo de señal desconocido: {tipo}")

    return {"ok": True}


# -- Endpoints de estado y metricas -------------------------------------------

@app.get("/api/folders")
def list_folders():
    configs = all_folder_configs()
    result  = {}
    for fid, cfg in configs.items():
        result[fid] = {
            "config":             cfg,
            "posiciones_abiertas": [
                {"symbol": sym, **pos}
                for (f, sym), pos in open_positions.items() if f == fid
            ],
        }
    return {"folders": result, "count": len(configs)}


@app.get("/api/folder/{folder_id}/status")
def folder_status(folder_id: str):
    if folder_id not in _FOLDER_IDS:
        raise HTTPException(status_code=404, detail=f"Carpeta '{folder_id}' no existe")
    cfg = load_folder_config(folder_id)
    pos = [{"symbol": sym, **p} for (f, sym), p in open_positions.items() if f == folder_id]
    return {"folder_id": folder_id, "config": cfg, "posiciones_abiertas": pos}


@app.get("/api/folder/{folder_id}/metrics")
def folder_metrics(folder_id: str):
    if folder_id not in _FOLDER_IDS:
        raise HTTPException(status_code=404, detail=f"Carpeta '{folder_id}' no existe")
    from manager.metrics import metrics_for_folder
    return metrics_for_folder(folder_id)


@app.get("/api/metrics")
def all_metrics():
    from manager.metrics import metrics_all
    return metrics_all()


@app.post("/api/folder/{folder_id}/report")
def generate_report(folder_id: str):
    if folder_id not in _FOLDER_IDS:
        raise HTTPException(status_code=404, detail=f"Carpeta '{folder_id}' no existe")
    from manager.metrics import generate_insights_md
    content = generate_insights_md(folder_id)
    return {"folder_id": folder_id, "report": content}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, reload=False)
