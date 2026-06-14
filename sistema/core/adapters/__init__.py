"""
Selector de adaptador por tipo de emisor.
"""
from core.adapters import (
    adapter_tradingview,
    adapter_generico,
    adapter_bot_grid,
    adapter_bot_manager,
)

_ADAPTERS = {
    "tradingview": adapter_tradingview,
    "generico":    adapter_generico,
    "bot_grid":    adapter_bot_grid,
    "bot_manager": adapter_bot_manager,
}


def get_adapter(emisor: str):
    """Retorna el modulo adaptador para el emisor dado, o el generico si no existe."""
    return _ADAPTERS.get(emisor, adapter_generico)
