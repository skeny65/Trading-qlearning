"""
Estrategia 4 - Worker Q-Learning.
Par: ETHUSDT  |  Indicadores: EMA9 / EMA21 / EMA200

Flujo de 2 alertas por operacion (igual que estrategias 1, 2, 3):
    Alerta 1 (signal_type: "open")  -> Q-Learning decide si ejecutar
    Alerta 2 (signal_type: "close") -> cierre inmediato + update Q

Estado 3D: f1_level | f2_level | f3_level  (3x3x3 = 27 estados)
    f1_level : wide (>=0.5%) | mid (>=0.2%) | tight (<0.2%)
               Separacion porcentual entre EMA9 y EMA21.

    f2_level : strong (>=0.5%) | mid (>=0.2%) | flat (<0.2%)
               Pendiente/angulo de EMA9 en %.

    f3_level : far (>=1.0%) | mid (>=0.3%) | near (<0.3%)
               Distancia del precio a EMA200 en %.

--- PAYLOAD APERTURA LARGO ---
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":    2845.5,
      "f1_sep":   0.123,
      "f2_angle": 0.087,
      "f3_d200":  1.452
    }
  }
}

--- PAYLOAD APERTURA CORTO ---
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "sell",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":    2845.5,
      "f1_sep":   0.123,
      "f2_angle": 0.087,
      "f3_d200":  1.452
    }
  }
}

--- PAYLOAD CIERRE LARGO ---
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        2820.0,
      "entry_price":  2845.5,
      "close_reason": "strategy_exit",
      "pnl_pct":      -0.9
    }
  }
}

--- PAYLOAD CIERRE CORTO ---
{
  "status": "pending",
  "signal": {
    "symbol":      "ETHUSDT",
    "action":      "close_sell",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        2820.0,
      "entry_price":  2845.5,
      "close_reason": "strategy_exit",
      "pnl_pct":      0.9
    }
  }
}

URL webhook:
    POST /webhook/strategy/4?secret=<TV_WEBHOOK_SECRET>
"""
from core.strategy_worker import StrategyWorker


class Strategy4Worker(StrategyWorker):
    strategy_id = "4"

    def encode_state(self, params: dict) -> str:
        """
        Estado 3D: f1_level|f2_level|f3_level
        Basado en EMA9/EMA21/EMA200 de ETHUSDT.
        """
        f1 = float(params.get("f1_sep",   0.0))
        f2 = float(params.get("f2_angle", 0.0))
        f3 = float(params.get("f3_d200",  0.0))

        # F1: separacion EMA9 vs EMA21
        if f1 >= 0.5:
            f1_level = "wide"
        elif f1 >= 0.2:
            f1_level = "mid"
        else:
            f1_level = "tight"

        # F2: angulo/pendiente EMA9
        if f2 >= 0.5:
            f2_level = "strong"
        elif f2 >= 0.2:
            f2_level = "mid"
        else:
            f2_level = "flat"

        # F3: distancia precio a EMA200
        if f3 >= 1.0:
            f3_level = "far"
        elif f3 >= 0.3:
            f3_level = "mid"
        else:
            f3_level = "near"

        return f"{f1_level}|{f2_level}|{f3_level}"
