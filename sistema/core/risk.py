"""
risk.py — Position sizing por riesgo fijo porcentual.

Fórmula:
    riesgo_usdt = balance * (risk_pct / 100)
    qty         = riesgo_usdt / sl_distance

Si el precio toca el SL la pérdida es exactamente risk_pct% del balance,
independientemente del apalancamiento usado.

Ejemplo con balance=314 USDT, risk=5%, sl_distance=22 USDT:
    riesgo_usdt = 314 * 0.05 = 15.70 USDT
    qty         = 15.70 / 22 = 0.7136 ETH
    verificación: 0.7136 * 22 = 15.70 USDT perdidos si toca SL  ✓
"""
from decimal import Decimal, ROUND_DOWN

MAX_RISK_PCT = 5.0  # techo duro — el bot nunca arriesga más de esto


def calcular_qty_por_riesgo(
    balance_usdt: float,
    risk_pct:     float,
    sl_distance:  float,
    price:        float,
    filters:      dict,
    max_risk_pct: float = MAX_RISK_PCT,
) -> tuple[float, float]:
    """
    Calcula la cantidad a operar para arriesgar exactamente risk_pct% del balance.

    Args:
        balance_usdt:  balance disponible en USDT (leído de Binance).
        risk_pct:      % del capital a arriesgar (ej: 5.0).
        sl_distance:   distancia en USDT entre entrada y SL (abs(price - sl)).
        price:         precio de entrada.
        filters:       dict de _get_filters() con keys step, min_qty, min_notional.
        max_risk_pct:  techo duro de riesgo.

    Returns:
        (qty, riesgo_usdt) — qty redondeada al stepSize de Binance.

    Raises:
        ValueError: si sl_distance <= 0, o qty/notional no cumplen mínimos.
    """
    if sl_distance <= 0:
        raise ValueError(f"sl_distance invalida: {sl_distance}")
    if balance_usdt <= 0:
        raise ValueError(f"balance invalido: {balance_usdt}")

    # Techo duro: nunca arriesgar más del máximo permitido
    risk_pct    = min(risk_pct, max_risk_pct)
    riesgo_usdt = balance_usdt * (risk_pct / 100.0)
    qty_raw     = riesgo_usdt / sl_distance

    # Redondear HACIA ABAJO al stepSize de Binance (evita rechazo de orden)
    step  = filters["step"]   # Decimal, viene de _get_filters()
    qty_d = (Decimal(str(qty_raw)) / step).to_integral_value(rounding=ROUND_DOWN) * step
    qty   = float(qty_d)

    if qty < float(filters["min_qty"]):
        raise ValueError(
            f"qty calculada {qty} < minQty {float(filters['min_qty'])} "
            f"(balance={balance_usdt:.2f} risk={risk_pct}% sl_dist={sl_distance:.4f})"
        )

    notional = qty * price
    if notional < float(filters["min_notional"]):
        raise ValueError(
            f"notional {notional:.2f} USDT < minNotional {float(filters['min_notional'])}"
        )

    return qty, riesgo_usdt
