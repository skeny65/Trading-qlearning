"""
bot_grid_poller.py - Monitor de señales BOT_GRID v2.0 via JSONL file polling.

Lee el archivo audit.jsonl de BOT_GRID cada N segundos usando tracking de offset
para evitar reprocesar señales anteriores. Maneja OPEN_GRID, ADJUST_GRID, CLOSE_GRID.

Carpeta 9 usa modo_cierre: "bot_grid" — este poller gestiona toda su logica de cierre.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import config
from core import binance_executor
from utils.excel_logger  import append_excel_row, update_excel_result
from utils               import balance_tracker

logger = logging.getLogger("bot3.bot_grid_poller")

POLL_INTERVAL_SEC = 2


class BotGridPoller:
    def __init__(self, open_positions: dict, folder_configs: dict):
        self._open_positions = open_positions
        self._configs        = folder_configs
        self._offsets: dict  = {}
        self._running        = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._run, daemon=True, name="bot-grid-poller"
        )
        self._thread.start()
        logger.info(f"BotGridPoller iniciado (intervalo={POLL_INTERVAL_SEC}s)")

    def stop(self):
        self._running = False
        logger.info("BotGridPoller detenido")

    def _run(self):
        while self._running:
            try:
                self._poll_all()
            except Exception as e:
                logger.error(f"BotGridPoller loop error: {e}")
            time.sleep(POLL_INTERVAL_SEC)

    # -------------------------------------------------------------------------
    # Polling
    # -------------------------------------------------------------------------

    def _poll_all(self):
        for folder_id, cfg in self._configs.items():
            if cfg.get("modo_cierre") != "bot_grid" or not cfg.get("enabled"):
                continue
            bg_cfg = cfg.get("bot_grid_config", {})
            path   = bg_cfg.get("audit_log_path", "")
            if not path:
                continue
            # Si la ruta es un directorio, resuelve el archivo del día actual
            if os.path.isdir(path):
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                path  = os.path.join(path, f"{today}.jsonl")
            self._poll_file(folder_id, cfg, path)

    def _poll_file(self, folder_id: str, cfg: dict, path: str):
        if not os.path.exists(path):
            return

        offset = self._offsets.get(path, 0)
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    self._offsets[path] = f.tell()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        signal = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(f"[{folder_id}] Linea JSONL invalida: {line[:80]}")
                        continue
                    self._process_signal(signal, folder_id, cfg)
        except Exception as e:
            logger.error(f"[{folder_id}] Error leyendo {path}: {e}")

    # -------------------------------------------------------------------------
    # Procesamiento
    # -------------------------------------------------------------------------

    def _process_signal(self, signal: dict, folder_id: str, cfg: dict):
        bg_cfg   = cfg.get("bot_grid_config", {})
        expected = bg_cfg.get("expected_version", "2.0")

        if signal.get("version") != expected:
            logger.warning(
                f"[{folder_id}] Version inesperada: {signal.get('version')} (esperada {expected})"
            )
            return

        max_age = bg_cfg.get("max_signal_age_seconds", 60)
        try:
            ts_str = signal.get("timestamp_utc", "")
            ts     = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age    = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > max_age:
                logger.warning(
                    f"[{folder_id}] TTL expirado signal_id={signal.get('signal_id', '?')} "
                    f"age={age:.0f}s > {max_age}s — descartado"
                )
                return
        except Exception:
            pass

        symbol     = signal.get("symbol", "")
        permitidos = cfg.get("symbols_permitidos", [])
        if permitidos and symbol not in permitidos:
            logger.warning(f"[{folder_id}] Symbol {symbol} no permitido — skip")
            return

        action = signal.get("action", "").upper()

        if action == "OPEN_GRID":
            self._handle_open(signal, folder_id, cfg)
        elif action == "CLOSE_GRID":
            self._handle_close(signal, folder_id, cfg)
        elif action == "ADJUST_GRID":
            self._handle_adjust(signal, folder_id, cfg)
        else:
            logger.warning(f"[{folder_id}] Accion desconocida: {action}")

    # -------------------------------------------------------------------------
    # Handlers
    # -------------------------------------------------------------------------

    def _handle_open(self, signal: dict, folder_id: str, cfg: dict):
        symbol     = signal["symbol"]
        params     = signal.get("params", {})
        sizing_cfg = cfg["sizing"]
        signal_id  = signal.get("signal_id", "")
        side       = params.get("side", "buy")
        price_base = float(params.get("price_base", 0))

        if (folder_id, symbol) in self._open_positions:
            logger.warning(f"[{folder_id}|{symbol}] OPEN_GRID: posicion ya abierta — skip")
            return

        dry_run    = config.DRY_RUN or not cfg.get("binance_live", False)
        mode_label = "DRY_RUN" if dry_run else "LIVE"

        if dry_run:
            order_id       = f"dry_grid_{symbol}_{signal_id[:8]}"
            binance_status = "dry_run"
            logger.info(
                f"[{folder_id}|{symbol}] DRY_RUN OPEN_GRID side={side} "
                f"price_base={price_base} levels={params.get('num_levels', 3)}"
            )
        else:
            result         = binance_executor.open_grid(symbol, side, params, sizing_cfg)
            binance_status = result["status"]
            order_id       = result.get("order_id", signal_id)
            if binance_status != "ok":
                logger.error(
                    f"[{folder_id}|{symbol}] OPEN_GRID Binance error: {result.get('detail', '')}"
                )

        open_time = datetime.now(timezone.utc).isoformat()

        self._open_positions[(folder_id, symbol)] = {
            "order_id":       order_id,
            "side":           side,
            "open_time":      open_time,
            "entry_price":    price_base,
            "sl":             params.get("sl"),
            "tp":             params.get("tp"),
            "sizing_cfg":     sizing_cfg,
            "binance_status": binance_status,
            "grid":           True,
            "signal_id":      signal_id,
        }

        bal_antes = balance_tracker.get_balance(folder_id)
        excel_row = {
            "timestamp_utc":  open_time,
            "event_id":       signal_id,
            "id_carpeta":     folder_id,
            "emisor":         "bot_grid",
            "mode":           mode_label,
            "symbol":         symbol,
            "side":           side,
            "price":          price_base,
            "sl":             params.get("sl", ""),
            "tp":             params.get("tp", ""),
            "margen_usdt":    sizing_cfg.get("margen_usdt", ""),
            "leverage":       sizing_cfg.get("leverage", ""),
            "order_id":       order_id,
            "binance_status": binance_status,
            "balance_antes":  round(bal_antes, 4),
        }
        try:
            append_excel_row(excel_row, folder_id)
        except Exception as e:
            logger.warning(f"[{folder_id}|{symbol}] Excel append error: {e}")

        logger.info(
            f"[{folder_id}|{symbol}] OPEN_GRID registrado order_id={order_id} "
            f"binance={binance_status}"
        )

    def _handle_close(self, signal: dict, folder_id: str, cfg: dict):
        symbol    = signal["symbol"]
        params    = signal.get("params", {})
        signal_id = signal.get("signal_id", "")

        open_pos = self._open_positions.pop((folder_id, symbol), None)

        dry_run = config.DRY_RUN or not cfg.get("binance_live", False)
        if not dry_run:
            binance_executor.close_grid_position(symbol)
        else:
            logger.info(f"[{folder_id}|{symbol}] DRY_RUN CLOSE_GRID")

        close_reason = params.get("close_reason", "CLOSE_GRID")
        pnl_pct      = params.get("pnl_pct")
        exit_price   = float(params.get("price_exit", 0))

        if pnl_pct is None and open_pos:
            entry = float(open_pos.get("entry_price", 0))
            side  = open_pos.get("side", "buy")
            if entry and exit_price:
                if side == "buy":
                    pnl_pct = round((exit_price - entry) / entry * 100, 4)
                else:
                    pnl_pct = round((entry - exit_price) / entry * 100, 4)

        resultado     = "WIN" if (pnl_pct or 0) > 0 else "LOSS"
        matched_order = (open_pos or {}).get("order_id", signal_id)

        # Calcular profit USDT y actualizar balance
        sz          = (open_pos or {}).get("sizing_cfg", cfg.get("sizing", {}))
        margen_usdt = float(sz.get("margen_usdt", 0) or 0)
        leverage    = float(sz.get("leverage",    1) or 1)
        profit_usdt = round(margen_usdt * leverage * (pnl_pct or 0) / 100, 4)
        bal_antes, bal_despues = balance_tracker.update_balance(folder_id, profit_usdt)

        try:
            update_excel_result(
                order_id        = matched_order,
                result          = resultado,
                strategy_id     = folder_id,
                pnl_pct         = f"{pnl_pct:+.4f}%" if pnl_pct is not None else "",
                pnl_notes       = f"{close_reason} | grid",
                precio_salida   = exit_price,
                duracion_min    = 0.0,
                profit_usdt     = profit_usdt,
                balance_antes   = bal_antes,
                balance_despues = bal_despues,
            )
        except Exception as e:
            logger.warning(f"[{folder_id}|{symbol}] Excel update error: {e}")

        logger.info(
            f"[{folder_id}|{symbol}] CLOSE_GRID {resultado} "
            f"pnl={pnl_pct if pnl_pct is not None else 'N/A'} reason={close_reason}"
        )

    def _handle_adjust(self, signal: dict, folder_id: str, cfg: dict):
        symbol    = signal["symbol"]
        params    = signal.get("params", {})
        signal_id = signal.get("signal_id", "")

        logger.info(f"[{folder_id}|{symbol}] ADJUST_GRID signal_id={signal_id}")

        dry_run = config.DRY_RUN or not cfg.get("binance_live", False)
        if dry_run:
            logger.info(f"[{folder_id}|{symbol}] DRY_RUN ADJUST_GRID — sin cambios en Binance")
            return

        result = binance_executor.adjust_grid(symbol, params, cfg["sizing"])
        logger.info(
            f"[{folder_id}|{symbol}] ADJUST_GRID: "
            f"{result.get('status')} {result.get('detail', '')}"
        )

    def get_status(self) -> dict:
        grid_folders = [
            fid for fid, cfg in self._configs.items()
            if cfg.get("modo_cierre") == "bot_grid" and cfg.get("enabled")
        ]
        return {
            "running":           self._running,
            "poll_interval_sec": POLL_INTERVAL_SEC,
            "grid_folders":      grid_folders,
            "file_offsets":      dict(self._offsets),
        }
