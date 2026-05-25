"""
Estrategia 1 (APUESTA) - Worker Q-Learning.
Indicadores: Brecha de medias + D300 en SOLUSDT (LIVE).

Estado 3D: brecha_level | pendiente_level | d300_level  (3x3x3 = 27 estados)

    brecha_level  : wide (>=0.5%) | mid (>=0.2%) | tight (<0.2%)
                    Separacion porcentual entre las medias (dist_brecha).
                    Mide compresion del mercado: tight = rango lateral.

    pendiente_level: strong (>=0.05%) | mid (>=0.02%) | flat (<0.02%)
                    Pendiente de la media verde (pendiente_verde).
                    Mide inercia: flat = sin impulso suficiente.

    d300_level    : far (>=1.0%) | mid (>=0.3%) | near (<0.3%)
                    Distancia del precio a la D300 (dist_d300).
                    Mide riesgo de iman institucional: near = zona peligrosa.

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
      "price":           85.30,
      "sl":              85.17,
      "dist_brecha":     0.142,
      "pendiente_verde": 0.038,
      "cierre_brecha":   0.051,
      "d300_trend":      "alcista",
      "dist_d300":       1.203,
      "slope":           "up"
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
      "price":        85.55,
      "entry_price":  85.30,
      "close_reason": "Cruce contrario",
      "pnl_pct":      0.29
    }
  }
}

close_reason posibles: "Cruce contrario" | "Stop Loss"
"""
from core.strategy_worker import StrategyWorker


class ApuestaWorker(StrategyWorker):
    strategy_id = "1"

    def encode_state(self, params: dict) -> str:
        """
        Estado 3D: brecha_level|pendiente_level|d300_level
        Basado en los indicadores del Pine Script de brecha + D300.
        """
        brecha    = float(params.get("dist_brecha",     0.0))
        pendiente = float(params.get("pendiente_verde", 0.0))
        d300      = float(params.get("dist_d300",       0.0))

        # F1: separacion entre medias
        if brecha >= 0.5:
            brecha_level = "wide"
        elif brecha >= 0.2:
            brecha_level = "mid"
        else:
            brecha_level = "tight"

        # F2: pendiente de la media verde
        if pendiente >= 0.05:
            pendiente_level = "strong"
        elif pendiente >= 0.02:
            pendiente_level = "mid"
        else:
            pendiente_level = "flat"

        # F3: distancia a la D300
        if d300 >= 1.0:
            d300_level = "far"
        elif d300 >= 0.3:
            d300_level = "mid"
        else:
            d300_level = "near"

        return f"{brecha_level}|{pendiente_level}|{d300_level}"
