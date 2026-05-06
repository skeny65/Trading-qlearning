"""
webhook_client.py - Envia senales a bot1 (patron identico a bot2).

Flujo:
  send(payload) -> POST bot1/webhook/bot3 con backoff 3 intentos
  retry_pending() -> reintenta pending_signals.json al inicio de ciclo

Estado: state/pending_signals.json
"""
import json
import logging
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger("bot3.webhook")

_MAX_RETRIES  = 3
_PENDING_FILE = Path("state") / "pending_signals.json"


def _load_pending() -> list:
    try:
        return json.loads(_PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_pending(signals: list) -> None:
    _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PENDING_FILE.write_text(json.dumps(signals, indent=2), encoding="utf-8")


def _save_to_pending(payload: dict) -> None:
    signals = _load_pending()
    signals.append(payload)
    _save_pending(signals)
    logger.info(f"Senal guardada como pendiente (total: {len(signals)})")


def _post(payload: dict, headers: dict) -> dict:
    """Envia con backoff exponencial. Retorna el resultado."""
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.post(
                config.WEBHOOK_URL,
                json=payload,
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            response = r.json()
            logger.info(f"Webhook OK (intento {attempt}): status={response.get('status')}")
            return response
        except requests.exceptions.ConnectionError as e:
            last_error = str(e)
            logger.warning(f"Intento {attempt}/{_MAX_RETRIES} - bot1 no disponible")
        except requests.exceptions.Timeout:
            last_error = "timeout"
            logger.warning(f"Intento {attempt}/{_MAX_RETRIES} - timeout")
        except requests.exceptions.HTTPError:
            logger.error(f"HTTP {r.status_code} de bot1: {r.text[:200]}")
            return {"status": "error", "http_code": r.status_code, "detail": r.text}
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error inesperado en webhook: {e}")

        if attempt < _MAX_RETRIES:
            time.sleep(5 * attempt)  # backoff: 5s, 10s, 15s

    return {"status": "failed", "error": last_error}


def send(payload: dict) -> dict:
    """Envia el payload a bot1. Maneja dry_run, rejected y fallos de red."""
    if config.DRY_RUN:
        symbol = (payload.get("signal") or {}).get("symbol", "?")
        action = (payload.get("signal") or {}).get("action", "?")
        logger.info(f"[DRY_RUN] Webhook NO enviado - {action.upper()} {symbol}")
        return {"status": "dry_run"}

    headers = {
        "Content-Type":    "application/json",
        "X-Webhook-Secret": config.WEBHOOK_SECRET,
    }
    response = _post(payload, headers)

    if isinstance(response, dict) and response.get("status") == "rejected":
        reason = response.get("reason", "sin razon")
        logger.warning(f"bot1 rechazo la senal: {reason}")
        return response

    if isinstance(response, dict) and response.get("status") == "received_no_signal":
        logger.info("bot1 confirmo recepcion de no_signal")
        return response

    if isinstance(response, dict) and response.get("status") == "failed":
        if payload.get("status") == "pending":
            _save_to_pending(payload)

    return response


def retry_pending() -> int:
    """Reintenta senales pendientes al inicio. Retorna cuantas se enviaron."""
    signals = _load_pending()
    if not signals:
        return 0

    logger.info(f"Reintentando {len(signals)} senal(es) pendiente(s)...")
    headers = {
        "Content-Type":    "application/json",
        "X-Webhook-Secret": config.WEBHOOK_SECRET,
    }
    remaining  = []
    sent_count = 0
    for payload in signals:
        response = _post(payload, headers)
        if isinstance(response, dict) and response.get("status") not in ("failed", "error"):
            sent_count += 1
        else:
            remaining.append(payload)

    _save_pending(remaining)
    if sent_count:
        logger.info(f"{sent_count} senal(es) pendiente(s) enviada(s) OK")
    return sent_count
