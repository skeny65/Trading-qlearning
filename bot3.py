"""
bot3.py - FastAPI entrypoint para Trading Bot 3 (Q-Learning).

Patron identico a bot2 (agente01.py):
  - Recibe alertas TradingView en /webhook/tv
  - Aplica Q-Learning para decidir accion
  - Envia senal a bot1 via sender/webhook_client.py  (POST /webhook/bot3)
  - Notifica via Telegram (sender/telegram_notifier.py)
  - Registra en state/decision_log.jsonl
  - Escribe reporte en logs/YYYY-MM-DD_HH-MM-SS.json
  - Acumula en logs/trade_log.xlsx (excel_logger.py)

Endpoints:
    GET  /                   health check rapido
    GET  /health             estado detallado
    POST /webhook/tv         senales TradingView -> Q-Learning -> bot1
    GET  /qlearning/status   estadisticas del agente
    GET  /qlearning/qtable   Q-table completa
    POST /qlearning/update   aprendizaje hindsight (posicion cerrada)
    POST /qlearning/pause    pausar agente
    POST /qlearning/resume   reanudar agente
    GET  /pending            decisiones pendientes de actualizacion Q
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
from excel_logger              import append_excel_rows
from manager.qlearning_trainer import QLearningTrainer
from sender                    import webhook_client, signal_formatter, telegram_notifier
from strategies.strategy_tv_qlearning import TVQLearningStrategy
from utils.logger              import setup_logger

logger = setup_logger("bot3")

# -- globals -------------------------------------------------------------------

agent:    Optional[QLearningAgent]      = None
trainer:  Optional[QLearningTrainer]   = None
strategy: Optional[TVQLearningStrategy] = None

# {order_id: {state, action, timestamp, ticker, original_side, executed_side}}
pending_q_decisions: dict = {}

# -- helpers de persistencia (patron bot2) -------------------------------------

_DECISION_LOG = Path("state") / "decision_log.jsonl"


def _log_decision(entry: dict) -> None:
    """Append una decision a state/decision_log.jsonl."""
    _DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    try:
        with open(_DECISION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"No se pudo escribir decision_log: {e}")


def _write_event_report(report: dict) -> None:
    """Escribe un reporte JSON en logs/YYYY-MM-DD_HH-MM-SS.json."""
    Path("logs").mkdir(parents=True, exist_ok=True)
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    fpath   = Path("logs") / f"{ts}.json"
    try:
        fpath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"No se pudo escribir reporte: {e}")


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
    params = envelope_signal.params
    return {
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
        "event_id":       event_id,
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


# -- lifespan ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, trainer, strategy

    # Crear directorios necesarios
    for d in ("logs", "state", "data/qlearning"):
        Path(d).mkdir(parents=True, exist_ok=True)

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

    telegram_notifier.startup(config.DRY_RUN, config.PORT)

    yield

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


def _check_secret(secret: Optional[str]):
    if not config.TV_WEBHOOK_SECRET:
        logger.warning("TV_WEBHOOK_SECRET no configurado - aceptando todo (INSEGURO)")
        return
    if secret != config.TV_WEBHOOK_SECRET:
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
    """
    _check_ip(request)
    _check_secret(x_webhook_secret)

    try:
        body = await request.json()
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
        background_tasks.add_task(append_excel_rows, [excel_row])
        background_tasks.add_task(_write_event_report, {**log_entry, "dry_run": config.DRY_RUN})

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

    # -- Enviar a bot1 (patron bot2: send + manejo de respuesta) --------------
    wh_response     = webhook_client.send(payload)
    webhook_status  = wh_response.get("status", "unknown")
    order_id        = wh_response.get("order_id", event_id)

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

    # -- Tracking para hindsight learning --------------------------------------
    if agent and webhook_status in ("dry_run", "executed"):
        pending_q_decisions[order_id] = {
            "state":         state,
            "action":        ql_action,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "ticker":        ticker,
            "original_side": original_action,
            "executed_side": side,
        }

    # -- Persistencia (patron bot2: decision_log + Excel + reporte) -----------
    log_entry = {
        "event_id":      event_id,
        "decision":      "EXECUTE" if webhook_status in ("dry_run", "executed") else "FAILED",
        "ql_action":     ql_action,
        "symbol":        ticker,
        "action":        side,
        "state":         state,
        "q_value":       q_value,
        "size":          final_size,
        "webhook_status": webhook_status,
        "order_id":      order_id,
        "reason":        decision["reason"],
        "dry_run":       config.DRY_RUN,
    }
    _log_decision(log_entry)

    excel_row = _build_excel_row(
        event_id, ticker, original_action, decision, True, webhook_status, order_id, signal
    )
    background_tasks.add_task(append_excel_rows, [excel_row])
    background_tasks.add_task(_write_event_report, log_entry)

    if trainer:
        background_tasks.add_task(trainer.save_and_backup)

    return {
        "ticker":          ticker,
        "original_action": original_action,
        "ql_action":       ql_action,
        "state":           state,
        "q_value":         q_value,
        "execute":         True,
        "side":            side,
        "size":            final_size,
        "status":          webhook_status,
        "order_id":        order_id,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, reload=False)
