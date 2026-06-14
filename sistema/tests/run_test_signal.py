"""
run_test_signal.py - Envia señales de prueba al bot_ejecutor en DRY_RUN.

Simula el flujo completo: señal TradingView → webhook → open → close.

USO:
    python run_test_signal.py
    python run_test_signal.py --carpeta 4 --symbol ETHUSDT --action sell
    python run_test_signal.py --solo-open
    python run_test_signal.py --host http://localhost:8001
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------

def _post(url: str, body: dict, secret: str = "") -> dict:
    data    = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-webhook-secret"] = secret
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": e.code, "detail": body}
    except Exception as e:
        return {"error": str(e)}


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _sep(title: str = ""):
    print("\n" + "=" * 55)
    if title:
        print(f"  {title}")
        print("=" * 55)


def run(
    host:      str  = "http://localhost:8001",
    carpeta:   str  = "1",
    symbol:    str  = "SOLUSDT",
    action:    str  = "buy",
    price:     float = 155.20,
    sl:        float = 150.00,
    tp:        float = 165.00,
    close_px:  float = 165.00,
    secret:    str  = "",
    solo_open: bool = False,
):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _sep(f"bot_ejecutor v2 - Test Signal ({now})")
    print(f"  Host    : {host}")
    print(f"  Carpeta : {carpeta}")
    print(f"  Symbol  : {symbol}")
    print(f"  Action  : {action}")
    print(f"  Price   : {price}  SL: {sl}  TP: {tp}")

    # --- Salud ---
    health = _get(f"{host}/health")
    if "error" in health:
        print(f"\n[ERROR] Bot no disponible: {health}")
        sys.exit(1)

    dry_run = health.get("dry_run", "?")
    print(f"\n  Bot OK  : dry_run={dry_run}")
    if not dry_run:
        print("  [ADVERTENCIA] El bot NO está en DRY_RUN — se enviarán órdenes REALES")

    # --- Open ---
    _sep("1. OPEN")
    open_body = {
        "status": "pending",
        "signal": {
            "symbol": symbol,
            "action": action,
            "signal_type": "open",
            "size": 0.1,
            "params": {"price": price, "sl": sl, "tp": tp},
        },
    }
    url      = f"{host}/webhook/{carpeta}"
    r_open   = _post(url, open_body, secret)
    print(f"  POST {url}")
    print(f"  Response: {json.dumps(r_open, indent=2)}")

    if solo_open:
        print("\n  [--solo-open] Deteniendo tras el open.")
        return

    if "error" in r_open or r_open.get("skipped"):
        print("\n  [SKIP] Open no se ejecutó — abortando secuencia.")
        return

    print("\n  Esperando 1s antes del close...")
    time.sleep(1)

    # --- Close ---
    _sep("2. CLOSE")
    close_action = "close_sell" if action == "sell" else "close_buy"
    entry_px     = price
    if action == "buy":
        pnl_pct = round((close_px - entry_px) / entry_px * 100, 4)
    else:
        pnl_pct = round((entry_px - close_px) / entry_px * 100, 4)

    close_body = {
        "status": "pending",
        "signal": {
            "symbol": symbol,
            "action": close_action,
            "signal_type": "close",
            "size": 0.1,
            "params": {
                "price":        close_px,
                "entry_price":  entry_px,
                "pnl_pct":      pnl_pct,
                "close_reason": "test_script",
            },
        },
    }
    r_close = _post(url, close_body, secret)
    resultado = "WIN" if pnl_pct > 0 else "LOSS"
    print(f"  POST {url}")
    print(f"  Response: {json.dumps(r_close, indent=2)}")
    print(f"\n  Resultado esperado: {resultado} (pnl={pnl_pct:+.4f}%)")

    # --- Metricas ---
    _sep("3. Metricas post-ejecucion")
    metrics = _get(f"{host}/api/folder/{carpeta}/metrics")
    if "error" in metrics:
        print(f"  [ERROR] {metrics}")
    else:
        print(f"  Total trades : {metrics.get('total_trades', 0)}")
        print(f"  Wins         : {metrics.get('wins', 0)}")
        print(f"  Losses       : {metrics.get('losses', 0)}")
        print(f"  Winrate      : {metrics.get('winrate_pct', 0):.2f}%")
        print(f"  PnL acum.    : {metrics.get('pnl_acumulado', 0):+.4f}%")

    _sep("FIN")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test signal bot_ejecutor v2 (DRY_RUN)")
    parser.add_argument("--host",      default="http://localhost:8001")
    parser.add_argument("--carpeta",   default="1")
    parser.add_argument("--symbol",    default="SOLUSDT")
    parser.add_argument("--action",    default="buy",  choices=["buy", "sell"])
    parser.add_argument("--price",     default=155.20, type=float)
    parser.add_argument("--sl",        default=150.00, type=float)
    parser.add_argument("--tp",        default=165.00, type=float)
    parser.add_argument("--close-px",  default=165.00, type=float, dest="close_px")
    parser.add_argument("--secret",    default="")
    parser.add_argument("--solo-open", action="store_true", dest="solo_open")
    args = parser.parse_args()
    run(**vars(args))
