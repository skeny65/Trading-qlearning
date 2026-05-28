"""
price_poller.py - Monitor independiente de posiciones abiertas.

Filosofia:
  - 100% independiente de Alpaca, TradingView o cualquier broker
  - Consulta precio actual desde Binance public REST (sin API key)
  - Detecta automaticamente cuando una posicion toca TP o SL
  - Dispara el update de Q-Learning sin intervencion humana

Fuente de precio:
  Binance public API: GET https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT
  - Gratuita, sin autenticacion, actualizada en tiempo real
  - Funciona para cualquier par de crypto en Binance

Scope:
  Solo monitorea estrategias 4-10. Las estrategias 1, 2 y 3 gestionan su propio
  cierre via alerta TradingView (signal_type="close") — el Poller las ignora para
  evitar doble aprendizaje. Ver SELF_CLOSING_STRATEGIES.

Flujo (estrategias 4-10):
  1. bot3 abre trade → guarda en pending_q_decisions con entry/sl/tp
  2. PricePoller corre cada POLL_INTERVAL_SEC
  3. Para cada pending (excluye estrategias 1,2,3): obtiene precio de Binance
  4. Si precio >= TP (buy) o <= TP (sell) → TP HIT
  5. Si precio <= SL (buy) o >= SL (sell) → SL HIT
  6. Calcula PnL%, llama worker.update_q() → Q-table aprende
  7. Remueve de pending_q_decisions
"""
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from core.reward_calculator import compute_reward
from utils.excel_logger     import update_excel_result

logger = logging.getLogger("bot3.price_poller")

BINANCE_PRICE_URL     = "https://api.binance.com/api/v3/ticker/price"
POLL_INTERVAL_SEC     = 60      # revisar posiciones cada 60 segundos
MAX_TRADE_DURATION_H  = 24      # cerrar forzado si lleva mas de 24h abierto
PRICE_FETCH_TIMEOUT   = 5       # timeout de red en segundos

# Estrategias que gestionan su propio cierre via alerta TradingView (signal_type="close").
# El Poller NO debe interferir con ellas — el Q-update lo dispara la alerta de cierre.
SELF_CLOSING_STRATEGIES = {"1", "2", "3", "4"}


class PricePoller:
    """
    Background thread que monitorea posiciones abiertas contra precio Binance.
    Se inicia en el lifespan de bot3 y corre hasta que el bot se apaga.
    """

    def __init__(self, pending_q_decisions: dict, registry):
        self._pending  = pending_q_decisions   # referencia al dict de bot3
        self._registry = registry              # StrategyRegistry
        self._running  = False
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            daemon=True,
            name="price-poller",
        )
        self._thread.start()
        logger.info(f"PricePoller iniciado (intervalo={POLL_INTERVAL_SEC}s)")

    def stop(self):
        self._running = False
        logger.info("PricePoller detenido")

    # -------------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------------

    def _run(self):
        while self._running:
            try:
                self._check_all_positions()
            except Exception as e:
                logger.error(f"PricePoller loop error: {e}")
            time.sleep(POLL_INTERVAL_SEC)

    def _check_all_positions(self):
        if not self._pending:
            return

        # Snapshot para evitar mutacion durante iteracion.
        # Excluir estrategias que cierran via alerta TradingView (1, 2, 3).
        order_ids = list(self._pending.keys())
        activas = [
            oid for oid in order_ids
            if "entry_price" in self._pending.get(oid, {})
            and self._pending[oid].get("strategy_id", "") not in SELF_CLOSING_STRATEGIES
        ]

        if not activas:
            return

        logger.debug(f"PricePoller: revisando {len(activas)} posicion(es) abiertas (excluye 1,2,3)")

        for order_id in activas:
            pending = self._pending.get(order_id)
            if not pending:
                continue

            symbol      = pending["symbol"]
            side        = pending["side"]
            entry       = float(pending["entry_price"])
            sl          = float(pending["sl"])
            tp          = float(pending["tp"])
            open_time   = pending["open_time"]
            state       = pending["state"]
            action      = pending["action"]
            strategy_id = pending.get("strategy_id", "qlearning")

            # -- Duracion acumulada
            try:
                open_dt      = datetime.fromisoformat(open_time)
                duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60
            except Exception:
                duration_min = 0.0

            # -- Expirar si lleva demasiado tiempo
            if duration_min > MAX_TRADE_DURATION_H * 60:
                logger.warning(
                    f"[{order_id}] Trade expirado tras {duration_min:.0f}min "
                    f"({MAX_TRADE_DURATION_H}h limite) - cerrando al precio actual"
                )
                current_price = self._get_price(symbol)
                if current_price:
                    self._close_position(order_id, pending, current_price, "EXPIRED", duration_min)
                continue

            # -- Precio actual
            current_price = self._get_price(symbol)
            if current_price is None:
                continue

            # -- Detectar TP / SL
            hit        = None
            exit_price = None

            if side == "buy":
                if current_price >= tp:
                    hit, exit_price = "TP", tp
                elif current_price <= sl:
                    hit, exit_price = "SL", sl
            else:  # sell
                if current_price <= tp:
                    hit, exit_price = "TP", tp
                elif current_price >= sl:
                    hit, exit_price = "SL", sl

            if hit:
                logger.info(
                    f"[{strategy_id}|{order_id}] {symbol} {hit} tocado! "
                    f"entry={entry} exit={exit_price} actual={current_price:.4f}"
                )
                self._close_position(order_id, pending, exit_price, hit, duration_min)
            else:
                dist_tp = abs(current_price - tp)
                dist_sl = abs(current_price - sl)
                logger.debug(
                    f"[{order_id}] {symbol} actual={current_price:.4f} | "
                    f"dist_TP={dist_tp:.4f} dist_SL={dist_sl:.4f} "
                    f"({duration_min:.0f}min abierto)"
                )

    # -------------------------------------------------------------------------
    # Close position: calcula reward y actualiza Q-table
    # -------------------------------------------------------------------------

    def _close_position(
        self,
        order_id:     str,
        pending:      dict,
        exit_price:   float,
        reason:       str,
        duration_min: float,
    ):
        strategy_id = pending.get("strategy_id", "qlearning")
        side        = pending["side"]
        entry       = float(pending["entry_price"])
        state       = pending["state"]
        action      = pending["action"]

        # -- PnL %
        if side == "buy":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        # -- R-multiple
        r_multiple = self._compute_r_multiple(pending, exit_price)

        # -- Reward
        reward = compute_reward({
            "pnl_pct":              pnl_pct,
            "duration_min":         duration_min,
            "account_drawdown_pct": 0.0,   # desconocido sin Alpaca
            "r_multiple":           r_multiple,
        })

        # -- Actualizar Q-table del worker correspondiente
        worker = self._registry.get(strategy_id)
        if not worker:
            logger.error(f"Worker '{strategy_id}' no encontrado para order {order_id}")
            self._pending.pop(order_id, None)
            return

        next_state = state   # el proximo estado se conocera en la proxima senal
        new_q      = worker.update_q(state, action, reward, next_state)

        # -- Remover de pendientes
        self._pending.pop(order_id, None)

        resultado  = "WIN" if pnl_pct > 0 else "LOSS"
        pnl_notes  = f"{reason} | {duration_min:.0f}min | R={r_multiple:.2f}x"

        logger.info(
            f"[{resultado}] [{strategy_id}|{order_id}] {reason}: "
            f"pnl={pnl_pct:+.2f}% R={r_multiple:.1f}x "
            f"reward={reward:.4f} new_q={new_q:.6f} "
            f"dur={duration_min:.0f}min"
        )

        # -- Actualizar Excel automaticamente con el resultado
        updated = update_excel_result(
            order_id    = order_id,
            result      = resultado,
            strategy_id = strategy_id,
            pnl_pct     = f"{pnl_pct:+.2f}%",
            pnl_notes   = pnl_notes,
        )
        if not updated:
            logger.debug(f"[{order_id}] Fila no encontrada en Excel (puede estar en otro ciclo)")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _compute_r_multiple(self, pending: dict, exit_price: float) -> float:
        entry = float(pending["entry_price"])
        sl    = float(pending["sl"])
        side  = pending["side"]

        risk = abs(entry - sl)
        if risk == 0:
            return 0.0

        gain = (exit_price - entry) if side == "buy" else (entry - exit_price)
        return round(gain / risk, 2)

    def _get_price(self, symbol: str) -> Optional[float]:
        """
        Consulta precio actual de Binance public API.
        Sin autenticacion, sin API key, completamente gratuito.
        Funciona para SOLUSDT, BTCUSDT, ETHUSD, etc.
        """
        try:
            url = f"{BINANCE_PRICE_URL}?symbol={symbol}"
            req = urllib.request.Request(url, headers={"User-Agent": "bot3-price-poller/1.0"})
            with urllib.request.urlopen(req, timeout=PRICE_FETCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                return float(data["price"])
        except Exception as e:
            logger.warning(f"No se pudo obtener precio de {symbol}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Introspection (para /health y /api/strategies)
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        activas = [
            oid for oid, p in self._pending.items()
            if "entry_price" in p
        ]
        return {
            "running":          self._running,
            "poll_interval_sec": POLL_INTERVAL_SEC,
            "monitored_trades": len(activas),
            "order_ids":        activas,
        }
