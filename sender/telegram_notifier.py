"""
telegram_notifier.py - Notificaciones Telegram (patron identico a bot2).

Funciones:
  signal_sent()     -> senal aprobada y ejecutada en bot1
  signal_rejected() -> bot1 rechazo la senal
  webhook_failed()  -> fallo de red, senal en cola
  signal_skipped()  -> Q-Learning descarto la senal (SKIP)
  agent_paused()    -> auto-pausa activada
  startup()         -> bot3 arrancado
"""
import logging
import requests

import config

logger = logging.getLogger("bot3.telegram")

_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def _send(text: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            _BASE,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        logger.debug(f"Telegram error (no critico): {e}")


def signal_sent(symbol: str, action: str, size: float, ql_action: str, state: str, dry_run: bool):
    mode = "DRY" if dry_run else "LIVE"
    _send(
        f"* <b>[BOT3 {mode}] Senal enviada a bot1</b>\n"
        f"  Simbolo  : {symbol}\n"
        f"  Accion   : {action.upper()}\n"
        f"  Tamano   : {size:.1%}\n"
        f"  QL Action: {ql_action}\n"
        f"  Estado   : {state}"
    )


def signal_rejected(symbol: str, reason: str):
    _send(
        f"* <b>[BOT3] Senal RECHAZADA por bot1</b>\n"
        f"  Simbolo: {symbol}\n"
        f"  Razon  : {reason}"
    )


def webhook_failed(symbol: str, error: str):
    _send(
        f"* <b>[BOT3] Fallo de red - senal en cola</b>\n"
        f"  Simbolo: {symbol}\n"
        f"  Error  : {error[:100]}"
    )


def signal_skipped(symbol: str, ql_action: str, state: str, q_value: float):
    _send(
        f"🔍 <b>[BOT3] Senal DESCARTADA por Q-Learning</b>\n"
        f"  Simbolo : {symbol}\n"
        f"  Accion  : {ql_action}\n"
        f"  Estado  : {state}\n"
        f"  Q-value : {q_value:.4f}"
    )


def agent_paused(reason: str):
    _send(
        f"🛑 <b>[BOT3] Agente Q-Learning AUTO-PAUSADO</b>\n"
        f"  Razon: {reason}"
    )


def startup(dry_run: bool, port: int):
    mode = "DRY RUN" if dry_run else "* LIVE"
    _send(
        f"🚀 <b>[BOT3] Bot3 Q-Learning arrancado</b>\n"
        f"  Modo  : {mode}\n"
        f"  Puerto: {port}\n"
        f"  URL   : http://localhost:{port}/webhook/tv"
    )
