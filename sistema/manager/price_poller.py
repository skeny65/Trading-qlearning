"""
price_poller.py - Monitor de posiciones abiertas para carpetas con modo_cierre != dos_senales.

Monitorea solo las carpetas configuradas con:
  - modo_cierre: "una_senal_poller" o "sltp_en_binance"

Las carpetas con modo_cierre: "dos_senales" (ej. TradingView 1-4) se ignoran
porque su cierre lo gestiona el emisor con una segunda señal.

Sin Q-Learning. Al detectar TP/SL solo actualiza Excel/JSONL.
"""
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from utils.excel_logger  import update_excel_result
from utils               import balance_tracker

logger = logging.getLogger("bot3.price_poller")

BINANCE_PRICE_URL    = "https://api.binance.com/api/v3/ticker/price"
POLL_INTERVAL_SEC    = 10
MAX_TRADE_DURATION_H = 24
PRICE_FETCH_TIMEOUT  = 5

# Modos de cierre que SI son monitoreados por el poller
POLLER_MODOS = {"una_senal_poller", "sltp_en_binance", "trailing_stop"}


class PricePoller:
    def __init__(self, pending_poller: dict, folder_configs: dict, open_positions: dict = None):
        self._pending        = pending_poller    # referencia al dict de bot3
        self._configs        = folder_configs    # {folder_id: cfg} para saber que carpetas monitorear
        self._open_positions = open_positions or {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True, name="price-poller")
        self._thread.start()
        logger.info(f"PricePoller iniciado (intervalo={POLL_INTERVAL_SEC}s)")

    def stop(self):
        self._running = False
        logger.info("PricePoller detenido")

    def _run(self):
        while self._running:
            try:
                self._check_all_positions()
            except Exception as e:
                logger.error(f"PricePoller loop error: {e}")
            time.sleep(POLL_INTERVAL_SEC)

    def _should_monitor(self, folder_id: str) -> bool:
        """True si la carpeta tiene un modo_cierre que requiere el poller."""
        cfg = self._configs.get(folder_id, {})
        return cfg.get("modo_cierre", "") in POLLER_MODOS

    def _check_all_positions(self):
        if not self._pending:
            return

        # Solo monitorear posiciones de carpetas configuradas para poller
        order_ids = list(self._pending.keys())
        activas   = [
            oid for oid in order_ids
            if self._pending.get(oid, {}).get("folder_id", "") and
               self._should_monitor(self._pending[oid]["folder_id"])
        ]

        if not activas:
            return

        logger.debug(f"PricePoller: revisando {len(activas)} posicion(es)")

        for order_id in activas:
            pending = self._pending.get(order_id)
            if not pending:
                continue

            folder_id  = pending["folder_id"]
            symbol     = pending["symbol"]
            side       = pending["side"]
            entry      = float(pending["entry_price"])
            sl         = float(pending.get("sl") or 0)
            tp         = float(pending.get("tp") or 0)
            open_time  = pending["open_time"]
            modo       = self._configs.get(folder_id, {}).get("modo_cierre", "")

            try:
                open_dt      = datetime.fromisoformat(open_time)
                duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60
            except Exception:
                duration_min = 0.0

            # Expirar tras MAX_TRADE_DURATION_H
            if duration_min > MAX_TRADE_DURATION_H * 60:
                logger.warning(f"[{order_id}] Trade expirado tras {duration_min:.0f}min")
                current_price = self._get_price(symbol)
                if current_price:
                    self._close_position(order_id, pending, current_price, "EXPIRED", duration_min)
                continue

            # Trailing stop: verificar si Binance todavía tiene la posición abierta
            if modo == "trailing_stop":
                self._check_trailing_stop(order_id, pending, symbol, entry, duration_min)
                continue

            # SL/TP fijo normal
            current_price = self._get_price(symbol)
            if current_price is None:
                continue

            hit = exit_price = None
            if sl > 0 and tp > 0:
                if side == "buy":
                    if current_price >= tp:
                        hit, exit_price = "TP", tp
                    elif current_price <= sl:
                        hit, exit_price = "SL", sl
                else:
                    if current_price <= tp:
                        hit, exit_price = "TP", tp
                    elif current_price >= sl:
                        hit, exit_price = "SL", sl

            if hit:
                logger.info(
                    f"[{folder_id}|{order_id}] {symbol} {hit} tocado! "
                    f"entry={entry} exit={exit_price} actual={current_price:.4f}"
                )
                self._close_position(order_id, pending, exit_price, hit, duration_min)
            else:
                logger.debug(
                    f"[{order_id}] {symbol} actual={current_price:.4f} "
                    f"({duration_min:.0f}min abierto)"
                )

    def _close_position(
        self,
        order_id:     str,
        pending:      dict,
        exit_price:   float,
        reason:       str,
        duration_min: float,
    ):
        folder_id = pending["folder_id"]
        side      = pending["side"]
        entry     = float(pending["entry_price"])

        if side == "buy":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        self._pending.pop(order_id, None)
        self._open_positions.pop((folder_id, symbol), None)

        resultado = "WIN" if pnl_pct > 0 else "LOSS"
        pnl_notes = f"{reason} | {duration_min:.0f}min"

        # Calcular profit USDT y actualizar balance
        pos_data    = pending or {}
        margen_usdt = float(pos_data.get("margen_usdt", 0) or 0)
        lev         = float(pos_data.get("leverage",    1) or 1)
        profit_usdt = round(margen_usdt * lev * pnl_pct / 100, 4) if margen_usdt else 0.0
        bal_antes, bal_despues = balance_tracker.update_balance(folder_id, profit_usdt)

        logger.info(
            f"[{resultado}] [{folder_id}|{order_id}] {reason}: "
            f"pnl={pnl_pct:+.2f}% profit={profit_usdt:+.4f} USDT "
            f"balance={bal_antes:.2f}→{bal_despues:.2f} dur={duration_min:.0f}min"
        )

        update_excel_result(
            order_id        = order_id,
            result          = resultado,
            strategy_id     = folder_id,
            pnl_pct         = f"{pnl_pct:+.2f}%",
            pnl_notes       = pnl_notes,
            precio_salida   = exit_price,
            duracion_min    = duration_min,
            profit_usdt     = profit_usdt,
            balance_antes   = bal_antes,
            balance_despues = bal_despues,
        )

    def _check_trailing_stop(
        self,
        order_id:     str,
        pending:      dict,
        symbol:       str,
        entry:        float,
        duration_min: float,
    ):
        """
        Trailing stop interno: rastrea el precio máximo (buy) o mínimo (sell) desde la apertura.
        Si el precio retrocede más del callback_rate% desde el pico → cierra via MARKET.
        No depende de Binance para colocar órdenes condicionales.
        """
        import os
        dry = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

        folder_id = pending["folder_id"]
        side      = pending["side"]

        # Obtener callback_rate: del pending (nuevo) o del config (migración)
        callback_pct = float(pending.get("callback_rate") or 0)
        if callback_pct <= 0:
            cfg      = self._configs.get(folder_id, {})
            ts_cfg   = cfg.get("trailing_stop", {})
            risk_pct = float(ts_cfg.get("risk_pct", 10.0))
            pct_b    = float(cfg.get("sizing", {}).get("pct", 95)) / 100
            lev      = float(cfg.get("sizing", {}).get("leverage", 25))
            callback_pct = risk_pct / (pct_b * lev)

        callback = callback_pct / 100  # porcentaje → decimal

        current_price = self._get_price(symbol)
        if current_price is None:
            return

        # Actualizar pico y verificar disparo
        peak = float(pending.get("peak_price") or entry)

        if side == "buy":
            if current_price > peak:
                pending["peak_price"] = current_price
                peak = current_price
            trigger = peak * (1 - callback)
            triggered = current_price <= trigger
        else:
            if current_price < peak:
                pending["peak_price"] = current_price
                peak = current_price
            trigger = peak * (1 + callback)
            triggered = current_price >= trigger

        if triggered:
            logger.info(
                f"[{folder_id}|{order_id}] {symbol} TRAILING STOP! "
                f"side={side} peak={peak:.2f} trigger={trigger:.2f} actual={current_price:.2f} "
                f"callback={callback_pct:.3f}%"
            )
            if not dry:
                try:
                    from core.binance_executor import close_position
                    res = close_position(symbol)
                    if res["status"] != "ok":
                        logger.error(f"[{order_id}] close_position fallo: {res['detail']}")
                except Exception as e:
                    logger.error(f"[{order_id}] Error cerrando posicion trailing: {e}")
            self._close_position(order_id, pending, current_price, "TRAILING_STOP", duration_min)
        else:
            dist_pct = abs(current_price - trigger) / trigger * 100
            logger.debug(
                f"[{order_id}] {symbol} trailing {side}: precio={current_price:.2f} "
                f"pico={peak:.2f} disparo={trigger:.2f} (+{dist_pct:.3f}% hasta TS) "
                f"({duration_min:.0f}min)"
            )

    def _get_price(self, symbol: str) -> Optional[float]:
        try:
            url = f"{BINANCE_PRICE_URL}?symbol={symbol}"
            req = urllib.request.Request(url, headers={"User-Agent": "bot-ejecutor-poller/2.0"})
            with urllib.request.urlopen(req, timeout=PRICE_FETCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                return float(data["price"])
        except Exception as e:
            logger.warning(f"No se pudo obtener precio de {symbol}: {e}")
            return None

    def get_status(self) -> dict:
        activas = list(self._pending.keys())
        return {
            "running":           self._running,
            "poll_interval_sec": POLL_INTERVAL_SEC,
            "monitored_trades":  len(activas),
            "order_ids":         activas,
        }
