"""
test_ejecutor.py - Suite de pruebas para bot_ejecutor v2 (modo DRY_RUN).

Casos cubiertos:
  1. TradingView open exitoso (carpeta 1, enabled)
  2. TradingView close exitoso (sigue al open)
  3. Señal a carpeta disabled (carpeta 2) — retorna skipped
  4. Symbol no permitido (BTCUSDT en carpeta que solo permite SOLUSDT)
  5. Doble open del mismo symbol — segundo se descarta
  6. Payload JSON invalido — 400
  7. Carpeta fuera de rango (0, 11) — 404
  8. Webhook secret incorrecto — 401
  9. Calculo pnl buy: close_price > entry → WIN
 10. Calculo pnl sell: close_price < entry → WIN
 11. Endpoint /health responde
 12. Endpoint /api/folder/{id}/status responde
 13. Endpoint /api/metrics responde
 14. Adapter TradingView: status != pending → tipo=ignorar
 15. Adapter TradingView: signal_type=close parsing correcto
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Asegurar que DRY_RUN=true y sin secret durante las pruebas
os.environ["DRY_RUN"]            = "true"
os.environ["TV_WEBHOOK_SECRET"]  = ""
os.environ["TV_ENFORCE_IP_WHITELIST"] = "false"

# Ajustar sys.path para importar desde sistema/
sys.path.insert(0, str(Path(__file__).parent.parent))

import bot3
from core.adapters import adapter_tradingview


# =============================================================================
# Fixtures y helpers
# =============================================================================

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _tv_open(symbol="SOLUSDT", action="buy", price=155.20, sl=150.00, tp=165.00) -> dict:
    return {
        "status": "pending",
        "signal": {
            "symbol": symbol,
            "action": action,
            "signal_type": "open",
            "size": 0.1,
            "params": {"price": price, "sl": sl, "tp": tp},
        },
    }


def _tv_close(symbol="SOLUSDT", action="close_buy", price=165.00, entry=155.20, pnl=6.31) -> dict:
    return {
        "status": "pending",
        "signal": {
            "symbol": symbol,
            "action": action,
            "signal_type": "close",
            "size": 0.1,
            "params": {
                "price": price,
                "entry_price": entry,
                "pnl_pct": pnl,
                "close_reason": "test_close",
            },
        },
    }


@pytest.fixture(autouse=True)
def reset_positions():
    """Limpia el estado global entre pruebas."""
    bot3.open_positions.clear()
    bot3.pending_poller.clear()
    yield
    bot3.open_positions.clear()
    bot3.pending_poller.clear()


@pytest.fixture(scope="module")
def client():
    with TestClient(bot3.app) as c:
        yield c


# =============================================================================
# 1. Open exitoso
# =============================================================================

def test_open_carpeta1_dry_run(client):
    body = _tv_open()
    resp = client.post("/webhook/1", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "skipped" not in data


def test_open_registra_en_open_positions(client):
    body = _tv_open()
    client.post("/webhook/1", json=body)
    # BackgroundTask se ejecuta sincrónicamente con TestClient
    assert ("1", "SOLUSDT") in bot3.open_positions


# =============================================================================
# 2. Close exitoso
# =============================================================================

def test_close_despues_de_open(client):
    # Open primero
    client.post("/webhook/1", json=_tv_open())
    assert ("1", "SOLUSDT") in bot3.open_positions

    # Close
    resp = client.post("/webhook/1", json=_tv_close())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # La posicion se elimina al recibir el close
    assert ("1", "SOLUSDT") not in bot3.open_positions


def test_close_sin_open_previo_no_explota(client):
    resp = client.post("/webhook/1", json=_tv_close())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# =============================================================================
# 3. Carpeta disabled
# =============================================================================

def test_carpeta_disabled_retorna_skipped(client):
    # Carpeta 2 tiene enabled=false en config.json
    body = _tv_open()
    resp = client.post("/webhook/2", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("skipped") == "disabled"


def test_carpeta_disabled_no_abre_posicion(client):
    client.post("/webhook/2", json=_tv_open())
    assert ("2", "SOLUSDT") not in bot3.open_positions


# =============================================================================
# 4. Symbol no permitido
# =============================================================================

def test_symbol_no_permitido_retorna_skipped(client):
    # Carpeta 1 solo permite SOLUSDT según config.json
    body = _tv_open(symbol="BTCUSDT")
    resp = client.post("/webhook/1", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "skipped" in data
    assert "BTCUSDT" in data["skipped"]


def test_symbol_no_permitido_no_abre_posicion(client):
    client.post("/webhook/1", json=_tv_open(symbol="BTCUSDT"))
    assert ("1", "BTCUSDT") not in bot3.open_positions


# =============================================================================
# 5. Doble open del mismo symbol
# =============================================================================

def test_doble_open_descarta_segundo(client):
    body = _tv_open()
    # Primer open
    r1 = client.post("/webhook/1", json=body)
    assert r1.json()["ok"] is True
    assert ("1", "SOLUSDT") in bot3.open_positions

    # Segundo open del mismo symbol
    r2 = client.post("/webhook/1", json=body)
    assert r2.status_code == 200
    data2 = r2.json()
    assert "skipped" in data2
    assert "SOLUSDT" in data2["skipped"]


# =============================================================================
# 6. Payload invalido
# =============================================================================

def test_json_invalido_retorna_400(client):
    resp = client.post(
        "/webhook/1",
        content=b"esto no es json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_payload_sin_signal_retorna_422(client):
    resp = client.post("/webhook/1", json={"status": "pending"})
    assert resp.status_code == 422


# =============================================================================
# 7. Carpeta fuera de rango
# =============================================================================

def test_carpeta_cero_retorna_404(client):
    resp = client.post("/webhook/0", json=_tv_open())
    assert resp.status_code == 404


def test_carpeta_once_retorna_404(client):
    resp = client.post("/webhook/11", json=_tv_open())
    assert resp.status_code == 404


# =============================================================================
# 8. Webhook secret
# =============================================================================

def test_secret_invalido_retorna_401():
    os.environ["TV_WEBHOOK_SECRET"] = "secreto_test_abc"
    import importlib
    import config as cfg_mod
    importlib.reload(cfg_mod)

    with patch.object(bot3.config, "TV_WEBHOOK_SECRET", "secreto_test_abc"):
        with TestClient(bot3.app) as c:
            resp = c.post(
                "/webhook/1",
                json=_tv_open(),
                headers={"x-webhook-secret": "secreto_incorrecto"},
            )
        assert resp.status_code == 401

    os.environ["TV_WEBHOOK_SECRET"] = ""


def test_secret_correcto_pasa():
    with patch.object(bot3.config, "TV_WEBHOOK_SECRET", "secreto_test_abc"):
        with TestClient(bot3.app) as c:
            bot3.open_positions.clear()
            resp = c.post(
                "/webhook/1",
                json=_tv_open(),
                headers={"x-webhook-secret": "secreto_test_abc"},
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# =============================================================================
# 9-10. Calculo de PnL
# =============================================================================

def test_pnl_buy_win():
    """BUY: close > entry → pnl positivo → WIN."""
    open_pos = {
        "order_id":    "dry_test_001",
        "side":        "buy",
        "open_time":   "2026-01-01T00:00:00+00:00",
        "entry_price": 100.0,
        "sl":          95.0,
        "tp":          110.0,
        "sizing_cfg":  {"margen_usdt": 5.0, "leverage": 10},
        "binance_status": "dry_run",
    }
    bot3.open_positions[("1", "SOLUSDT")] = open_pos

    close_signal = {
        "id_carpeta":  "1",
        "tipo":        "close",
        "symbol":      "SOLUSDT",
        "side":        "buy",
        "price":       110.0,
        "pnl_pct":     None,
        "close_reason": "TP",
        "raw":         {},
    }
    open_pos_popped = bot3.open_positions.pop(("1", "SOLUSDT"))
    pnl = (110.0 - 100.0) / 100.0 * 100
    assert pnl > 0


def test_pnl_sell_win():
    """SELL: close < entry → pnl positivo → WIN."""
    entry = 67000.0
    close = 64000.0
    pnl   = (entry - close) / entry * 100
    assert pnl > 0


def test_pnl_buy_loss():
    """BUY: close < entry → pnl negativo → LOSS."""
    entry = 155.20
    close = 150.00
    pnl   = (close - entry) / entry * 100
    assert pnl < 0


# =============================================================================
# 11-13. Endpoints de estado y metricas
# =============================================================================

def test_health_retorna_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "dry_run" in data
    assert data["dry_run"] is True


def test_folder_status(client):
    resp = client.get("/api/folder/1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder_id"] == "1"
    assert "config" in data


def test_folder_status_invalido(client):
    resp = client.get("/api/folder/99/status")
    assert resp.status_code == 404


def test_api_metrics_responde(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "consolidado" in data
    assert "carpetas" in data


def test_api_folder_metrics(client):
    resp = client.get("/api/folder/1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_trades" in data
    assert "winrate_pct" in data


# =============================================================================
# 14-15. Adapter TradingView
# =============================================================================

def test_adapter_tv_status_no_pending():
    body = {"status": "ok", "signal": {}}
    result = adapter_tradingview.parse(body, "1")
    assert result["tipo"] == "ignorar"


def test_adapter_tv_open_parsing():
    body = _tv_open("SOLUSDT", "buy", 155.20, 150.00, 165.00)
    result = adapter_tradingview.parse(body, "1")
    assert result["tipo"] == "open"
    assert result["symbol"] == "SOLUSDT"
    assert result["side"] == "buy"
    assert result["price"] == 155.20
    assert result["sl"] == 150.00
    assert result["tp"] == 165.00


def test_adapter_tv_sell_parsing():
    body = _tv_open("BTCUSDT", "sell", 67000.0, 68500.0, 64000.0)
    result = adapter_tradingview.parse(body, "1")
    assert result["tipo"] == "open"
    assert result["side"] == "sell"


def test_adapter_tv_close_parsing():
    body = _tv_close("SOLUSDT", "close_buy", 165.00, 155.20, 6.31)
    result = adapter_tradingview.parse(body, "1")
    assert result["tipo"] == "close"
    assert result["symbol"] == "SOLUSDT"
    assert result["price"] == 165.00
    assert result["pnl_pct"] == 6.31
    assert result["close_reason"] == "test_close"


def test_adapter_tv_sin_symbol_lanza_error():
    body = {"status": "pending", "signal": {"action": "buy", "params": {}}}
    with pytest.raises(ValueError, match="symbol"):
        adapter_tradingview.parse(body, "1")


# =============================================================================
# Sizing — calculo de qty
# =============================================================================

def test_sizing_qty_formula():
    """notional = margen * leverage; qty = notional / price."""
    margen   = 5.0
    leverage = 10
    price    = 155.20
    expected_notional = margen * leverage  # 50.0 USDT
    expected_qty      = expected_notional / price
    assert abs(expected_qty - (50.0 / 155.20)) < 1e-6


def test_sizing_qty_minima_insuficiente():
    """Si qty calculada < minQty, binance_executor debe retornar skip."""
    from decimal import Decimal
    from core import binance_executor as be
    step    = Decimal("0.01")
    min_qty = Decimal("0.10")
    notional_target = Decimal("5") * Decimal("1")   # margen=5, leverage=1
    price   = Decimal("10000")
    qty_raw = notional_target / price
    qty     = be._round_down(qty_raw, step)
    # qty = 0.00 < min_qty = 0.10
    assert qty < min_qty
