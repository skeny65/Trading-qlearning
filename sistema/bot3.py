"""
bot3.py - FastAPI entrypoint para Trading Bot 3 (Q-Learning Multi-Estrategia).

Endpoints heredados (backward-compat con estrategia 'qlearning'):
    GET  /                              health check rapido
    GET  /health                        estado detallado
    POST /webhook/tv                    senales TradingView -> qlearning worker -> bot1
    GET  /qlearning/status              estadisticas del agente qlearning
    GET  /qlearning/qtable              Q-table completa qlearning
    POST /qlearning/update              aprendizaje hindsight (posicion cerrada)
    POST /qlearning/pause               pausar agente qlearning
    POST /qlearning/resume              reanudar agente qlearning
    GET  /pending                       decisiones pendientes de actualizacion Q

Endpoints multi-estrategia (Apuesta / QLearning / Tanque):
    POST /webhook/strategy/{id}         senal TradingView para estrategia especifica
    GET  /api/strategy/{id}/status      estado del worker (Q-table, epsilon, alpha)
    POST /api/strategy/{id}/pause       pausar agente de la estrategia
    POST /api/strategy/{id}/resume      reanudar agente de la estrategia
    POST /api/strategy/{id}/update      hindsight update para la estrategia
    GET  /api/strategies                lista todas las estrategias registradas
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

from core.qlearning_agent      import QLearningAgent
from core.reward_calculator    import compute_reward
from core.tv_signal_parser     import parse_tv_envelope
from core.strategy_registry    import StrategyRegistry
from core                      import binance_executor
from manager.price_poller      import PricePoller
from utils.excel_logger        import append_excel_rows, update_excel_result
from manager.qlearning_trainer import QLearningTrainer
from sender                    import webhook_client, signal_formatter, telegram_notifier
from strategies.strategy_tv_qlearning import TVQLearningStrategy
from utils.logger              import setup_logger

logger = setup_logger("bot3")

# -- globals -------------------------------------------------------------------

agent:    Optional[QLearningAgent]      = None
trainer:  Optional[QLearningTrainer]   = None
strategy: Optional[TVQLearningStrategy] = None

# {order_id: {state, action, timestamp, ticker, original_side, executed_side,
#              strategy_id, symbol, side, entry_price, sl, tp, open_time}}
pending_q_decisions: dict = {}
# {(strategy_id, symbol): {state, action, order_id, open_time}} - para asociar cierres con aperturas
open_positions: dict = {}
poller: Optional[PricePoller] = None

# -- helpers de persistencia ---------------------------------------------------


def _decision_log_path(strategy_id: str) -> Path:
    return Path(config.strategy_actividades_dir(strategy_id)) / "decision_log.jsonl"


def _log_decision(entry: dict, strategy_id: str = "qlearning") -> None:
    """Append una decision a state/{strategy_id}/decision_log.jsonl."""
    path = _decision_log_path(strategy_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    entry.setdefault("strategy_id", strategy_id)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"No se pudo escribir decision_log [{strategy_id}]: {e}")


def _send_to_bot1_and_track(
    payload, event_id, ticker, side, final_size,
    ql_action, state, q_value, original_action, decision, signal,
):
    """Envia a bot1 y registra resultado. Corre en background para no bloquear TV."""
    wh_response    = webhook_client.send(payload)
    webhook_status = wh_response.get("status", "unknown")
    order_id       = wh_response.get("order_id", event_id)

    if webhook_status == "dry_run":
        order_id = f"dry_{ticker}_{event_id}"
        logger.info(f"[{ticker}] DRY_RUN - senal simulada: {ql_action} {side} size={final_size}")
        telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, True)
    elif webhook_status == "executed":
        logger.info(f"[{ticker}] bot1 ejecuto: {side} size={final_size} order={order_id}")
        telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, False)
    elif webhook_status == "rejected":
        reason = wh_response.get("reason", "sin razon")
        logger.warning(f"[{ticker}] bot1 rechazo: {reason}")
        telegram_notifier.signal_rejected(ticker, reason)
    elif webhook_status == "failed":
        error = wh_response.get("error", "error de red")
        logger.error(f"[{ticker}] Fallo de red - senal en cola: {error}")
        telegram_notifier.webhook_failed(ticker, error)

    if agent and webhook_status in ("dry_run", "executed"):
        pending_q_decisions[order_id] = {
            "state":         state,
            "action":        ql_action,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "ticker":        ticker,
            "original_side": original_action,
            "executed_side": side,
            # campos para PricePoller
            "strategy_id":   "qlearning",
            "symbol":        ticker,
            "side":          side,
            "entry_price":   getattr(getattr(signal, "params", None), "price", 0.0),
            "sl":            getattr(getattr(signal, "params", None), "sl",    0.0),
            "tp":            getattr(getattr(signal, "params", None), "tp",    0.0),
            "open_time":     datetime.now(timezone.utc).isoformat(),
        }

    log_entry = {
        "event_id":       event_id,
        "strategy_id":    "qlearning",
        "decision":       "EXECUTE" if webhook_status in ("dry_run", "executed") else "FAILED",
        "ql_action":      ql_action,
        "symbol":         ticker,
        "action":         side,
        "state":          state,
        "q_value":        q_value,
        "size":           final_size,
        "webhook_status": webhook_status,
        "order_id":       order_id,
        "reason":         decision["reason"],
        "dry_run":        config.DRY_RUN,
    }
    _log_decision(log_entry, strategy_id="qlearning")
    append_excel_rows(
        [_build_excel_row(event_id, ticker, original_action, decision, True, webhook_status, order_id, signal)],
        strategy_id="qlearning",
    )
    _write_event_report(log_entry, strategy_id="qlearning")
    if trainer:
        trainer.save_and_backup()


def _write_event_report(report: dict, strategy_id: str = "qlearning") -> None:
    """Escribe un reporte JSON en logs/{strategy_id}/events/YYYY-MM-DD_HH-MM-SS.json."""
    events_dir = Path(config.strategy_actividades_dir(strategy_id)) / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    fpath = events_dir / f"{ts}.json"
    try:
        fpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"No se pudo escribir reporte [{strategy_id}]: {e}")


def _build_excel_row(
    event_id: str,
    symbol: str,
    tv_action: str,
    decision: dict,
    execute: bool,
    webhook_status: str,
    order_id: str,
    envelope_signal,
) -> dict:
    """Fila Excel para el endpoint legacy /webhook/tv (TVEnvelope)."""
    params = envelope_signal.params
    return {
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "event_id":       event_id,
        "strategy_id":    "qlearning",
        "mode":           "DRY_RUN" if config.DRY_RUN else "LIVE",
        "symbol":         symbol,
        "tv_action":      tv_action,
        "ql_action":      decision.get("ql_action", ""),
        "ql_state":       decision.get("state", ""),
        "q_value":        round(decision.get("q_value", 0.0), 6),
        "regime":         params.regime,
        "volatility":     params.volatility,
        "momentum":       params.momentum,
        "price":          params.price,
        "sl":             params.sl,
        "tp":             params.tp,
        "atr":            params.atr,
        "execute":        execute,
        "final_action":   decision.get("side", "none") if execute else "none",
        "size":           envelope_signal.size * decision.get("size_multiplier", 0.0),
        "confidence":     envelope_signal.confidence,
        "webhook_status": webhook_status,
        "order_id":       order_id,
        "reason":         decision.get("reason", ""),
        "epsilon":        round(agent.epsilon, 6) if agent else "",
        "alpha":          round(agent.alpha,   6) if agent else "",
    }


def _build_excel_row_strategy(
    event_id:       str,
    decision:       dict,
    execute:        bool,
    webhook_status: str,
    order_id:       str,
    worker,
) -> dict:
    """Fila Excel para el endpoint /webhook/strategy/{id} (decision dict generico)."""
    params = decision.get("params", {})
    return {
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "event_id":       event_id,
        "strategy_id":    decision.get("strategy_id", ""),
        "mode":           "DRY_RUN" if config.DRY_RUN else "LIVE",
        "symbol":         decision.get("symbol", ""),
        "tv_action":      decision.get("original_action", ""),
        "ql_action":      decision.get("ql_action", ""),
        "ql_state":       decision.get("state", ""),
        "q_value":        round(decision.get("q_value", 0.0), 6),
        "regime":         params.get("regime",     ""),
        "volatility":     params.get("volatility", ""),
        "momentum":       params.get("momentum",   ""),
        "price":          params.get("price",      0.0),
        "sl":             params.get("sl",         0.0),
        "tp":             params.get("tp",         0.0),
        "atr":            params.get("atr",        0.0),
        "execute":        execute,
        "final_action":   decision.get("side", "none") if execute else "none",
        "size":           decision.get("size", 0.0),
        "confidence":     decision.get("confidence", 0.0),
        "webhook_status": webhook_status,
        "order_id":       order_id,
        "reason":         decision.get("reason", ""),
        "epsilon":        round(worker.agent.epsilon, 6) if worker else "",
        "alpha":          round(worker.agent.alpha,   6) if worker else "",
        # Pre-llenadas como PENDING hasta que llegue el cierre
        "result":         "PENDING",
        "pnl_pct":        "PENDING",
        "pnl_notes":      "PENDING",
        "learned_at":     "",
    }


# -- lifespan ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, trainer, strategy, poller

    # Crear directorios necesarios — una carpeta por estrategia (1-10)
    _STRATEGY_IDS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    for sid in _STRATEGY_IDS:
        Path(config.strategy_data_dir(sid)).mkdir(parents=True, exist_ok=True)
        act = Path(config.strategy_actividades_dir(sid))
        act.mkdir(parents=True, exist_ok=True)
        (act / "events").mkdir(parents=True, exist_ok=True)
        (act / "backups").mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Arrancando bot3 - DRY_RUN={config.DRY_RUN}, "
        f"QLEARNING={config.QLEARNING_ENABLED}, PORT={config.PORT}"
    )

    # Reintentar senales pendientes de ciclos anteriores (patron bot2)
    retried = webhook_client.retry_pending()
    if retried:
        logger.info(f"Senales pendientes reintentadas al inicio: {retried}")

    if config.QLEARNING_ENABLED:
        agent    = QLearningAgent()
        trainer  = QLearningTrainer(agent)
        strategy = TVQLearningStrategy(agent)
        logger.info(
            f"Q-Learning inicializado: eps={agent.epsilon:.4f} "
            f"alpha={agent.alpha:.4f} paused={agent.paused}"
        )

    # Inicializar registry multi-estrategia
    StrategyRegistry.initialize_all()
    logger.info(f"Estrategias registradas: {StrategyRegistry.list_all()}")

    # Arrancar price poller (monitor independiente de posiciones)
    poller = PricePoller(pending_q_decisions, StrategyRegistry)
    poller.start()

    telegram_notifier.startup(config.DRY_RUN, config.PORT)

    yield

    if poller:
        poller.stop()
    if agent:
        agent.save()
        logger.info("Q-table guardada al cerrar")


app = FastAPI(
    title="Trading Bot 3 - Q-Learning",
    version="1.0.0",
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
    # Acepta el secreto tanto en header X-Webhook-Secret como en ?secret= (URL query param)
    if secret == config.TV_WEBHOOK_SECRET or query_secret == config.TV_WEBHOOK_SECRET:
        return
    raise HTTPException(status_code=401, detail="Webhook secret invalido")


# -- routes --------------------------------------------------------------------


@app.get("/")
def root():
    return {"status": "ok", "bot": "bot3-qlearning", "version": "1.0.0"}


@app.get("/health")
def health():
    return {
        "status":            "ok",
        "dry_run":           config.DRY_RUN,
        "qlearning_enabled": config.QLEARNING_ENABLED,
        "agent_paused":      agent.paused   if agent else None,
        "epsilon":           round(agent.epsilon, 4) if agent else None,
        "alpha":             round(agent.alpha,   4) if agent else None,
        "pending_decisions": len(pending_q_decisions),
        "price_poller":      poller.get_status() if poller else None,
        "strategies":        StrategyRegistry.list_all(),
        "webhook_url":       config.WEBHOOK_URL,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }


@app.post("/webhook/tv")
async def webhook_tv(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Recibe alertas TradingView, aplica Q-Learning y envia a bot1.
    Patron identico a bot2: log + Excel + Telegram por cada evento.
    Acepta secreto via header X-Webhook-Secret o query param ?secret=
    """
    _check_ip(request)
    query_secret = request.query_params.get("secret")
    _check_secret(x_webhook_secret, query_secret)

    try:
        raw = await request.body()
        body = json.loads(raw.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")

    logger.info(
        f"TV webhook recibido: source={body.get('source')} "
        f"status={body.get('status')}"
    )

    # Reconocer envelopes que no son pending (sin accion)
    if body.get("status") != "pending":
        return {
            "status":    "received_no_signal_tv",
            "detail":    f"status={body.get('status')} - sin accion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        envelope = parse_tv_envelope(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Envelope invalido: {e}")

    signal          = envelope.signal
    ticker          = signal.symbol
    original_action = signal.action
    params          = signal.params

    # -- Q-Learning decision ---------------------------------------------------
    if not agent or not strategy:
        decision = {
            "ql_action":       "EXECUTE_FULL",
            "state":           "unknown",
            "execute":         True,
            "side":            original_action,
            "size_multiplier": 1.0,
            "reason":          "Q-Learning desactivado - ejecutando senal original",
            "q_value":         0.0,
        }
    else:
        decision = strategy.decide(envelope)

    ql_action       = decision["ql_action"]
    execute         = decision["execute"]
    side            = decision["side"]
    size_multiplier = decision["size_multiplier"]
    state           = decision["state"]
    q_value         = decision.get("q_value", 0.0)
    final_size      = round(signal.size * size_multiplier, 4)

    event_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    # -- Si Q-Learning descarta la senal --------------------------------------
    if not execute:
        logger.info(f"[{ticker}] Senal descartada por Q-Learning: {ql_action}")
        telegram_notifier.signal_skipped(ticker, ql_action, state, q_value)

        log_entry = {
            "event_id":  event_id,
            "decision":  "SKIP",
            "ql_action": ql_action,
            "symbol":    ticker,
            "state":     state,
            "q_value":   q_value,
            "reason":    decision["reason"],
        }
        _log_decision(log_entry)

        excel_row = _build_excel_row(
            event_id, ticker, original_action, decision, False, "skipped", "", signal
        )
        background_tasks.add_task(append_excel_rows, [excel_row], "qlearning")
        background_tasks.add_task(_write_event_report, {**log_entry, "dry_run": config.DRY_RUN}, "qlearning")

        return {
            "ticker":          ticker,
            "original_action": original_action,
            "ql_action":       ql_action,
            "state":           state,
            "q_value":         q_value,
            "execute":         False,
            "status":          "skipped_by_qlearning",
            "reason":          decision["reason"],
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

    # -- Construir payload para bot1 (patron bot2) -----------------------------
    payload = signal_formatter.build_payload(
        symbol     = ticker,
        action     = side,
        confidence = signal.confidence,
        size       = final_size,
        ql_action  = ql_action,
        ql_state   = state,
        q_value    = q_value,
        regime     = params.regime,
        volatility = params.volatility,
        momentum   = params.momentum,
        price      = params.price,
        sl         = params.sl,
        tp         = params.tp,
        atr        = params.atr,
    )

    # -- Enviar a bot1 en BACKGROUND para no bloquear la respuesta a TradingView
    # TradingView tiene timeout de ~5s; el retry a bot1 puede tardar 45s+
    background_tasks.add_task(
        _send_to_bot1_and_track,
        payload, event_id, ticker, side, final_size,
        ql_action, state, q_value, original_action, decision, signal,
    )

    # Responder a TradingView inmediatamente
    return {
        "ticker":          ticker,
        "original_action": original_action,
        "ql_action":       ql_action,
        "state":           state,
        "q_value":         q_value,
        "execute":         True,
        "side":            side,
        "size":            final_size,
        "status":          "queued",
        "event_id":        event_id,
        "dry_run":         config.DRY_RUN,
        "reason":          decision["reason"],
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }


@app.get("/qlearning/status")
def qlearning_status():
    if not agent:
        return {"error": "Q-Learning no activado"}
    return trainer.get_summary() if trainer else {"paused": agent.paused}


@app.get("/qlearning/qtable")
def get_qtable():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    return {"q_table": agent.q_table, "states": len(agent.q_table)}


class UpdateRequest(BaseModel):
    order_id:             str
    pnl_pct:              float
    duration_min:         float = 0.0
    account_drawdown_pct: float = 0.0
    r_multiple:           float = 0.0
    next_state:           Optional[str] = None
    # Campos opcionales para learn_from_excel.py:
    # permiten actualizar sin necesitar order_id en pending_q_decisions
    state:                Optional[str] = None
    action:               Optional[str] = None


@app.post("/qlearning/update")
async def manual_update(req: UpdateRequest):
    """Aprendizaje hindsight cuando una posicion se cierra."""
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")

    if req.order_id not in pending_q_decisions:
        raise HTTPException(
            status_code=404,
            detail=f"Order '{req.order_id}' no encontrada en decisiones pendientes",
        )

    pending    = pending_q_decisions.pop(req.order_id)
    state      = pending["state"]
    action     = pending["action"]

    trade_result = {
        "pnl_pct":              req.pnl_pct,
        "duration_min":         req.duration_min,
        "account_drawdown_pct": req.account_drawdown_pct,
        "r_multiple":           req.r_multiple,
    }
    reward     = compute_reward(trade_result)
    next_state = req.next_state or state

    new_q = agent.update(state, action, reward, next_state)
    agent.decay_params()
    agent.record_reward(reward)

    if agent.check_degradation():
        agent.paused = True
        logger.warning("Auto-pausa activada por degradacion de rendimiento")
        telegram_notifier.agent_paused(f"win_rate bajo umbral en {agent._auto_pause_window} trades")

    if trainer:
        trainer.append_experience(state, action, reward, next_state)

    agent.save()

    _log_decision({
        "event_id": f"update_{req.order_id}",
        "decision": "HINDSIGHT_UPDATE",
        "state":    state,
        "action":   action,
        "reward":   reward,
        "new_q":    round(new_q, 6),
        "pnl_pct":  req.pnl_pct,
    })

    return {
        "order_id":    req.order_id,
        "state":       state,
        "action":      action,
        "pnl_pct":     req.pnl_pct,
        "reward":      reward,
        "new_q_value": round(new_q, 6),
        "next_state":  next_state,
        "agent_paused": agent.paused,
        "alpha":       round(agent.alpha,   6),
        "epsilon":     round(agent.epsilon, 6),
    }


@app.get("/pending")
def get_pending():
    return {"pending": pending_q_decisions, "count": len(pending_q_decisions)}


@app.post("/qlearning/pause")
def pause_agent():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    agent.paused = True
    agent.save()
    return {"status": "paused"}


@app.post("/qlearning/resume")
def resume_agent():
    if not agent:
        raise HTTPException(status_code=503, detail="Q-Learning no activado")
    agent.paused = False
    agent.save()
    return {"status": "resumed"}


# =============================================================================
# MULTI-STRATEGY ENDPOINTS
# =============================================================================

def _send_strategy_to_bot1(
    payload: dict,
    event_id: str,
    decision: dict,
    worker,
):
    """Background task: ejecuta la orden en Binance Futures directamente."""
    strategy_id = decision["strategy_id"]
    ticker      = decision["symbol"]
    side        = decision["side"]
    final_size  = decision["size"]
    ql_action   = decision["ql_action"]
    state       = decision["state"]
    q_value     = decision["q_value"]
    params      = decision.get("params", {})

    price = float(params.get("price", 0.0))
    sl    = float(params.get("sl",    0.0))
    tp    = float(params.get("tp",    0.0))

    # Estrategias en modo solo-aprendizaje (reciben señales pero no ejecutan en Binance)
    LEARN_ONLY_STRATEGIES = {"2", "3"}
    # Estrategias con flujo 2-alertas: TradingView gestiona SL/TP y envia close alert
    # No colocar SL/TP en Binance — TradingView cierra con signal_type:"close"
    SELF_CLOSING_STRATEGIES = {"1", "2", "3", "4"}

    simulate = config.DRY_RUN or strategy_id in LEARN_ONLY_STRATEGIES

    # Para estrategias de 2 alertas, ignorar sl/tp — TradingView los gestiona
    binance_sl = None if strategy_id in SELF_CLOSING_STRATEGIES else (sl or None)
    binance_tp = None if strategy_id in SELF_CLOSING_STRATEGIES else (tp or None)

    # --- Ejecutar en Binance (o simular) ---
    if simulate:
        order_id       = f"dry_{ticker}_{event_id}"
        webhook_status = "dry_run"
        mode_label     = "LEARN_ONLY" if strategy_id in LEARN_ONLY_STRATEGIES else "DRY_RUN"
        logger.info(f"[{strategy_id}|{ticker}] {mode_label}: {ql_action} {side} price={price}")
        telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, True)
    else:
        result         = binance_executor.open_position(ticker, side, price, binance_sl, binance_tp)
        binance_status = result["status"]
        order_id       = result.get("order_id") or event_id
        detail         = result.get("detail", "")

        if binance_status == "ok":
            webhook_status = "executed"
            logger.info(f"[{strategy_id}|{ticker}] Binance ejecuto: {side} {detail} order={order_id}")
            telegram_notifier.signal_sent(ticker, side, final_size, ql_action, state, False)
        elif binance_status == "skip":
            webhook_status = "rejected"
            logger.warning(f"[{strategy_id}|{ticker}] Binance skip: {detail}")
            telegram_notifier.signal_rejected(ticker, detail)
        else:
            webhook_status = "failed"
            logger.error(f"[{strategy_id}|{ticker}] Binance error: {detail}")
            telegram_notifier.webhook_failed(ticker, detail)

    # --- Tracking para Q-Learning y Price Poller ---
    open_time = datetime.now(timezone.utc).isoformat()
    pending_q_decisions[order_id] = {
        "state":         state,
        "action":        ql_action,
        "timestamp":     open_time,
        "ticker":        ticker,
        "original_side": decision["original_action"],
        "executed_side": side,
        "strategy_id":   strategy_id,
        "symbol":        ticker,
        "side":          side,
        "entry_price":   price,
        "sl":            sl,
        "tp":            tp,
        "open_time":     open_time,
        "binance_status": webhook_status,
    }
    # Indice secundario para asociar señales de cierre de TradingView con esta apertura
    open_positions[(strategy_id, ticker)] = {
        "order_id":    order_id,
        "state":       state,
        "action":      ql_action,
        "side":        side,
        "open_time":   open_time,
        "entry_price": price,
    }

    log_entry = {
        "event_id":       event_id,
        "strategy_id":    strategy_id,
        "decision":       "EXECUTE" if webhook_status in ("dry_run", "executed") else "FAILED",
        "ql_action":      ql_action,
        "symbol":         ticker,
        "action":         side,
        "state":          state,
        "q_value":        q_value,
        "size":           final_size,
        "webhook_status": webhook_status,
        "order_id":       order_id,
        "reason":         decision["reason"],
        "dry_run":        config.DRY_RUN,
    }
    _log_decision(log_entry, strategy_id=strategy_id)
    append_excel_rows(
        [_build_excel_row_strategy(event_id, decision, True, webhook_status, order_id, worker)],
        strategy_id=strategy_id,
    )
    _write_event_report(log_entry, strategy_id=strategy_id)
    worker.trainer.save_and_backup()


def _send_close_to_bot1(
    close_payload: dict,
    event_id:      str,
    strategy_id:   str,
    symbol:        str,
    open_pos:      dict,
    pnl_pct:       float,
    close_price:   float,
    close_reason:  str,
    worker,
):
    """Background task: cierra posicion en Binance, actualiza Q-table y Excel inmediatamente."""
    LEARN_ONLY_STRATEGIES = {"2", "3"}
    simulate = config.DRY_RUN or strategy_id in LEARN_ONLY_STRATEGIES

    if simulate:
        mode_label = "LEARN_ONLY" if strategy_id in LEARN_ONLY_STRATEGIES else "DRY_RUN"
        logger.info(f"[{strategy_id}|{symbol}] {mode_label} CLOSE: pnl={pnl_pct:+.2f}% reason={close_reason}")
    else:
        result = binance_executor.close_position(symbol)
        logger.info(
            f"[{strategy_id}|{symbol}] Binance close: status={result['status']} "
            f"pnl={pnl_pct:+.2f}% reason={close_reason} detail={result.get('detail','')}"
        )

    # Calcular duracion desde apertura
    try:
        open_dt      = datetime.fromisoformat(open_pos["open_time"].replace("Z", "+00:00"))
        duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60
    except Exception:
        duration_min = 0.0

    # Calcular recompensa y actualizar Q-table inmediatamente
    reward = compute_reward({
        "pnl_pct":             pnl_pct,
        "duration_min":        duration_min,
        "account_drawdown_pct": 0.0,
        "r_multiple":          0.0,
    })

    new_q = worker.update_q(
        state      = open_pos["state"],
        action     = open_pos["action"],
        reward     = reward,
        next_state = "closed",
        trade_meta = {
            "close_reason": close_reason,
            "pnl_pct":      pnl_pct,
            "symbol":       symbol,
            "duration_min": duration_min,
        },
    )

    # Rellenar Excel con resultado final
    resultado = "WIN" if pnl_pct > 0 else "LOSS"
    pnl_notes = f"{close_reason.upper()} | {duration_min:.0f}min"
    update_excel_result(
        order_id    = open_pos["order_id"],
        result      = resultado,
        strategy_id = strategy_id,
        pnl_pct     = f"{pnl_pct:+.2f}%",
        pnl_notes   = pnl_notes,
    )

    # Limpiar de pending_q_decisions (ya aprendimos)
    pending_q_decisions.pop(open_pos["order_id"], None)

    logger.info(
        f"[{strategy_id}|{symbol}] Q actualizado: {resultado} "
        f"reward={reward:.4f} new_q={new_q:.4f} eps={worker.agent.epsilon:.4f}"
    )
    telegram_notifier.signal_sent(
        symbol, "close", 0, f"{resultado} {pnl_pct:+.2f}%", open_pos["state"], False
    )


@app.post("/webhook/strategy/{strategy_id}")
async def webhook_strategy(
    strategy_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Recibe alertas TradingView para una estrategia especifica.
    Ruta: POST /webhook/strategy/apuesta | /webhook/strategy/qlearning | /webhook/strategy/tanque
    """
    _check_ip(request)
    query_secret = request.query_params.get("secret")
    _check_secret(x_webhook_secret, query_secret)

    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{strategy_id}' no registrada. Disponibles: {StrategyRegistry.list_all()}",
        )

    try:
        raw  = await request.body()
        body = json.loads(raw.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")

    logger.info(
        f"[{strategy_id}] TV webhook recibido: source={body.get('source')} "
        f"status={body.get('status')}"
    )

    if body.get("status") != "pending":
        return {
            "status":    "received_no_signal",
            "strategy":  strategy_id,
            "detail":    f"status={body.get('status')} - sin accion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # -- Routing por signal_type -------------------------------------------------
    signal_body = body.get("signal", {})
    signal_type = str(signal_body.get("signal_type", "open")).lower()

    if signal_type == "close":
        # Señal de cierre: bypass Q-Learning, cerrar posicion inmediatamente
        params_close  = signal_body.get("params", {})
        symbol_close  = str(signal_body.get("symbol", "UNKNOWN")).upper()
        action_close  = str(signal_body.get("action", "close_buy")).lower()
        close_price   = float(params_close.get("price",       0.0))
        entry_price   = float(params_close.get("entry_price", 0.0))
        pnl_pct_close = float(params_close.get("pnl_pct",     0.0))
        close_reason  = str(params_close.get("close_reason",  "cross"))
        close_size    = float(signal_body.get("size", 0.1))
        event_id_c    = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

        # Si pnl_pct no vino en el payload, calcularlo de entry_price vs close_price
        if pnl_pct_close == 0.0 and entry_price != 0.0:
            pnl_pct_close = round((close_price - entry_price) / entry_price * 100, 4)
            if "sell" in action_close:
                pnl_pct_close = -pnl_pct_close

        # Recuperar apertura asociada
        open_pos = open_positions.pop((strategy_id, symbol_close), None)

        logger.info(
            f"[{strategy_id}|{symbol_close}] CLOSE recibido: {action_close} "
            f"price={close_price} pnl={pnl_pct_close:+.2f}% reason={close_reason} "
            f"open_found={open_pos is not None}"
        )

        if open_pos:
            background_tasks.add_task(
                _send_close_to_bot1,
                {}, event_id_c, strategy_id, symbol_close,
                open_pos, pnl_pct_close, close_price, close_reason, worker,
            )
            close_status = "close_queued"
        else:
            # No habia apertura rastreada (bot reiniciado o señal de apertura no ejecutada)
            logger.warning(
                f"[{strategy_id}|{symbol_close}] CLOSE sin apertura rastreada - "
                f"actualizando Q manualmente si pnl_pct disponible"
            )
            close_status = "close_no_open_tracked"

        return {"ok": True}
    # ---------------------------------------------------------------------------

    try:
        decision = worker.decide(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error al procesar senal: {e}")

    ticker          = decision["symbol"]
    original_action = decision["original_action"]
    ql_action       = decision["ql_action"]
    execute         = decision["execute"]
    side            = decision["side"]
    state           = decision["state"]
    q_value         = decision["q_value"]
    final_size      = decision["size"]

    event_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    # -- Si Q-Learning descarta la senal --
    if not execute:
        logger.info(f"[{strategy_id}|{ticker}] Senal descartada: {ql_action}")
        telegram_notifier.signal_skipped(ticker, ql_action, state, q_value)

        log_entry = {
            "event_id":    event_id,
            "strategy_id": strategy_id,
            "decision":    "SKIP",
            "ql_action":   ql_action,
            "symbol":      ticker,
            "state":       state,
            "q_value":     q_value,
            "reason":      decision["reason"],
        }
        _log_decision(log_entry, strategy_id=strategy_id)
        excel_row = _build_excel_row_strategy(event_id, decision, False, "skipped", "", worker)
        background_tasks.add_task(append_excel_rows, [excel_row], strategy_id)
        background_tasks.add_task(_write_event_report, {**log_entry, "dry_run": config.DRY_RUN}, strategy_id)

        return {"ok": True}

    # Ejecutar en Binance directo (background para no bloquear TradingView)
    background_tasks.add_task(
        _send_strategy_to_bot1,
        {}, event_id, decision, worker,
    )

    return {"ok": True}


@app.get("/api/strategies")
def list_strategies():
    """Lista todas las estrategias registradas y su estado."""
    result = {}
    for sid in StrategyRegistry.list_all():
        w = StrategyRegistry.get(sid)
        result[sid] = w.get_status() if w else {"error": "worker not found"}
    return {"strategies": result, "count": len(result)}


@app.get("/api/strategy/{strategy_id}/status")
def strategy_status(strategy_id: str):
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    return worker.get_status()


@app.post("/api/strategy/{strategy_id}/pause")
def strategy_pause(strategy_id: str):
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    worker.agent.paused = True
    worker.agent.save()
    return {"strategy": strategy_id, "status": "paused"}


@app.post("/api/strategy/{strategy_id}/resume")
def strategy_resume(strategy_id: str):
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    worker.agent.paused = False
    worker.agent.save()
    return {"strategy": strategy_id, "status": "resumed"}


@app.post("/api/strategy/{strategy_id}/update")
async def strategy_update(strategy_id: str, req: UpdateRequest):
    """Hindsight Q-Learning update para una estrategia especifica."""
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")

    # Si vienen state y action directos (desde learn_from_excel.py), los usamos sin
    # necesitar que el order_id este en pending_q_decisions.
    if req.state and req.action:
        state  = req.state
        action = req.action
        pending_q_decisions.pop(req.order_id, None)  # limpiar si existia
    elif req.order_id in pending_q_decisions:
        pending = pending_q_decisions.pop(req.order_id)
        if pending.get("strategy_id") != strategy_id:
            raise HTTPException(
                status_code=400,
                detail=f"Order '{req.order_id}' pertenece a '{pending.get('strategy_id')}', no '{strategy_id}'",
            )
        state  = pending["state"]
        action = pending["action"]
    else:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Order '{req.order_id}' no encontrada. "
                "Pasa 'state' y 'action' directamente para actualizar sin pendiente."
            ),
        )

    next_state = req.next_state or state

    trade_result = {
        "pnl_pct":              req.pnl_pct,
        "duration_min":         req.duration_min,
        "account_drawdown_pct": req.account_drawdown_pct,
        "r_multiple":           req.r_multiple,
    }
    reward = compute_reward(trade_result)
    new_q  = worker.update_q(state, action, reward, next_state)

    if worker.agent.check_degradation():
        worker.agent.paused = True
        logger.warning(f"[{strategy_id}] Auto-pausa activada por degradacion")
        telegram_notifier.agent_paused(f"[{strategy_id}] win_rate bajo umbral")

    _log_decision({
        "event_id":    f"update_{req.order_id}",
        "strategy_id": strategy_id,
        "decision":    "HINDSIGHT_UPDATE",
        "state":       state,
        "action":      action,
        "reward":      reward,
        "new_q":       round(new_q, 6),
        "pnl_pct":     req.pnl_pct,
    })

    return {
        "strategy":    strategy_id,
        "order_id":    req.order_id,
        "state":       state,
        "action":      action,
        "pnl_pct":     req.pnl_pct,
        "reward":      reward,
        "new_q_value": round(new_q, 6),
        "next_state":  next_state,
        "agent_paused": worker.agent.paused,
        "alpha":       round(worker.agent.alpha,   6),
        "epsilon":     round(worker.agent.epsilon, 6),
    }


@app.get("/api/strategy/{strategy_id}/journal")
def strategy_journal(strategy_id: str, n: int = 20):
    """Ultimas N entradas del diario de aprendizaje de una estrategia."""
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    return worker.journal.get_summary(worker.agent.q_table)


@app.get("/api/strategy/{strategy_id}/journal/recent")
def strategy_journal_recent(strategy_id: str, n: int = 20):
    """Ultimas N entradas raw del journal."""
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    return {"entries": worker.journal.get_recent(n), "count": n}


@app.post("/api/strategy/{strategy_id}/journal/report")
def strategy_journal_report(strategy_id: str):
    """Genera el reporte diario .md para la estrategia y lo retorna."""
    worker = StrategyRegistry.get(strategy_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' no encontrada")
    content = worker.journal.generate_daily_report(
        q_table=worker.agent.q_table,
        agent_stats={"epsilon": worker.agent.epsilon, "alpha": worker.agent.alpha},
    )
    return {"strategy": strategy_id, "report": content}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, reload=False)
