"""
telegram_notifier.py - Notificaciones Telegram para bot_ejecutor v2.

Funciones:
  signal_sent()     -> posicion abierta / cerrada
  signal_rejected() -> señal descartada (skip)
  webhook_failed()  -> error en Binance
  startup()         -> bot arrancado
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


def signal_sent(symbol: str, action: str, size: float, resultado: str, notes: str, dry_run: bool):
    mode = "DRY" if dry_run else "LIVE"
    _send(
        f"<b>[BOT_EJECUTOR {mode}] {action.upper()} {symbol}</b>\n"
        f"  Resultado: {resultado}\n"
        f"  Margen   : {size} USDT\n"
        f"  Notas    : {notes or '—'}"
    )


def signal_rejected(symbol: str, reason: str):
    _send(
        f"<b>[BOT_EJECUTOR] SKIP {symbol}</b>\n"
        f"  Razon: {reason}"
    )


def webhook_failed(symbol: str, error: str):
    _send(
        f"<b>[BOT_EJECUTOR] ERROR {symbol}</b>\n"
        f"  Binance: {error[:120]}"
    )


def startup(dry_run: bool, port: int):
    mode = "DRY RUN" if dry_run else "LIVE"
    _send(
        f"<b>[BOT_EJECUTOR] Arrancado</b>\n"
        f"  Modo  : {mode}\n"
        f"  Puerto: {port}\n"
        f"  URL   : http://localhost:{port}/webhook/{{1-10}}"
    )
