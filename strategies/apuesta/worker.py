"""
Estrategia 1 (APUESTA) - Worker Q-Learning.
Logica: TEMA 21/55 + DEMA 200 en 10 minutos (v019).

Estado 3D: f1_level | f2_level | f3_level  (3x3x3 = 27 estados)
    f1_level : wide (>=0.5%) | mid (>=0.2%) | tight (<0.2%)
               Separacion porcentual entre TEMA21 y TEMA55.
               Mide compresion del mercado: tight = rango lateral.

    f2_level : strong (>=0.5%) | mid (>=0.2%) | flat (<0.2%)
               Angulo/pendiente de TEMA21 en 5 velas.
               Mide inercia: flat = sin impulso suficiente.

    f3_level : far (>=1.0%) | mid (>=0.3%) | near (<0.3%)
               Distancia del precio a la DEMA200.
               Mide riesgo de imán institucional: near = zona peligrosa.

Flujo de 2 alertas por operacion:
    Alerta 1 (signal_type: "open")  -> Q-Learning decide si ejecutar
    Alerta 2 (signal_type: "close") -> cierre inmediato + update Q

Payload apertura (TradingView):
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "buy",
    "signal_type": "open",
    "size":        0.1,
    "params": {
      "price":        91.57,
      "f1_sep":       0.627,
      "f2_angle":     0.906,
      "f3_d200":      1.701,
      "anti_parallel":"libre",
      "d200_trend":   "bajista",
      "slope":        "up"
    }
  }
}

Payload cierre (TradingView):
{
  "status": "pending",
  "signal": {
    "symbol":      "SOLUSDT",
    "action":      "close_buy",
    "signal_type": "close",
    "size":        0.1,
    "params": {
      "price":        91.30,
      "entry_price":  91.57,
      "close_reason": "cross",
      "pnl_pct":      -0.29
    }
  }
}
"""
from core.strategy_worker import StrategyWorker


class ApuestaWorker(StrategyWorker):
    strategy_id = "1"

    def encode_state(self, params: dict) -> str:
        """
        Estado 3D: f1_level|f2_level|f3_level
        Basado en los filtros reales del Pine Script TEMA 21/55 + DEMA 200.
        """
        f1 = float(params.get("f1_sep",   0.0))
        f2 = float(params.get("f2_angle", 0.0))
        f3 = float(params.get("f3_d200",  0.0))

        # F1: separacion TEMA21 vs TEMA55
        if f1 >= 0.5:
            f1_level = "wide"
        elif f1 >= 0.2:
            f1_level = "mid"
        else:
            f1_level = "tight"

        # F2: angulo/pendiente TEMA21
        if f2 >= 0.5:
            f2_level = "strong"
        elif f2 >= 0.2:
            f2_level = "mid"
        else:
            f2_level = "flat"

        # F3: distancia precio a DEMA200
        if f3 >= 1.0:
            f3_level = "far"
        elif f3 >= 0.3:
            f3_level = "mid"
        else:
            f3_level = "near"

        return f"{f1_level}|{f2_level}|{f3_level}"
