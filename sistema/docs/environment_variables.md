# Variables de Entorno — bot_ejecutor v2

Archivo: `sistema/.env` (copiar de `.env.example`).

---

## Servidor

| Variable | Default | Descripcion                      |
|----------|---------|----------------------------------|
| PORT     | 8001    | Puerto del servidor FastAPI       |
| DRY_RUN  | true    | Si true, simula sin ejecutar en Binance |

---

## Seguridad webhook

| Variable                  | Default | Descripcion                                  |
|--------------------------|---------|----------------------------------------------|
| TV_WEBHOOK_SECRET        | (vacio) | Secret que TradingView envia en el header    |
| TV_ENFORCE_IP_WHITELIST  | false   | Si true, solo acepta IPs de TradingView      |
| TV_ALLOWED_IPS           | (vacio) | IPs permitidas (coma-separadas)              |

IPs de TradingView: `52.89.214.238, 34.212.75.30, 54.218.53.128, 52.32.178.7`

---

## Binance Futures

| Variable                   | Default | Descripcion                              |
|---------------------------|---------|------------------------------------------|
| BINANCE_API_KEY           |         | API key de Binance Futures USDT-M        |
| BINANCE_API_SECRET        |         | API secret de Binance Futures USDT-M     |
| BINANCE_TESTNET           | true    | Usar testnet de Binance                  |
| BINANCE_DEFAULT_LEVERAGE  | 10      | Leverage cuando config.json no lo define |
| BINANCE_DEFAULT_MARGIN_USDT| 5.0   | Margen USDT cuando config.json no lo define |
| BINANCE_MAX_MARGIN_PCT    | 0.95    | Cap de seguridad: margen / balance libre |

---

## Telegram (opcional)

| Variable          | Default | Descripcion             |
|------------------|---------|-------------------------|
| TELEGRAM_BOT_TOKEN | (vacio) | Token del bot          |
| TELEGRAM_CHAT_ID   | (vacio) | Chat/grupo destino     |

Si ambos estan vacios, las notificaciones se desactivan silenciosamente.

---

## Sizing por carpeta

El sizing se define en `estrategias/estrategia_{id}/config.json`, no en `.env`.
Las variables `BINANCE_DEFAULT_*` solo aplican si el config.json de la carpeta no las define.

```json
{
  "sizing": {
    "tipo": "margen_fijo_usdt",
    "margen_usdt": 5.0,
    "leverage": 10
  }
}
```
