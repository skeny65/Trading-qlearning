# Variables de Entorno — bot_ejecutor

Archivo: `.env` en la raiz del proyecto.

---

## Binance Futures (requerido)

| Variable             | Valor actual | Descripcion                                          |
|----------------------|--------------|------------------------------------------------------|
| BINANCE_API_KEY      | (tu key)     | API Key de Binance — requiere permisos de Futuros    |
| BINANCE_API_SECRET   | (tu secret)  | API Secret de Binance                                |
| BINANCE_TESTNET      | false        | `true` = usar testnet (paper trading)                |
| BINANCE_LEVERAGE     | 25           | Apalancamiento para todas las ordenes                |
| BINANCE_MAX_MARGIN_PCT | 0.95       | % del balance disponible a usar (0.95 = 95%). 0.99 causa error "Margin is insufficient" por fees |

**Nota:** El bot consulta el balance en vivo antes de cada trade y usa el 95% del disponible.
No hay margen fijo — es siempre todo el balance con efecto compuesto automatico.

---

## Servidor

| Variable        | Valor  | Descripcion                              |
|-----------------|--------|------------------------------------------|
| PORT            | 8001   | Puerto del servidor FastAPI              |
| DRY_RUN         | false  | `true` = simula sin enviar ordenes reales|

---

## TradingView Webhook

| Variable                | Valor                  | Descripcion                              |
|-------------------------|------------------------|------------------------------------------|
| TV_WEBHOOK_SECRET       | mi_secreto_webhook_123 | Secret que TradingView envia en la alerta|
| TV_ENFORCE_IP_WHITELIST | false                  | `true` = solo acepta IPs de TradingView  |
| TV_ALLOWED_IPS          | (IPs oficiales TV)     | Lista de IPs permitidas                  |

---

## Telegram (opcional)

| Variable           | Valor | Descripcion                    |
|--------------------|-------|--------------------------------|
| TELEGRAM_BOT_TOKEN | -     | Token del bot de Telegram      |
| TELEGRAM_CHAT_ID   | -     | Chat ID para notificaciones    |

Si no se configuran, las notificaciones se omiten silenciosamente.

---

## Motor de Decision (ejecutor)

| Variable                  | Valor | Descripcion                                      |
|---------------------------|-------|--------------------------------------------------|
| QLEARNING_ENABLED         | true  | `false` = desactiva el motor de decision         |
| QLEARNING_ALPHA_INITIAL   | 0.10  | Tasa de aprendizaje inicial                      |
| QLEARNING_GAMMA           | 0.90  | Factor de descuento (importancia del futuro)     |
| QLEARNING_EPSILON_INITIAL | 0.20  | Exploracion inicial (20% de decisiones random)   |
| QLEARNING_EPSILON_MIN     | 0.02  | Exploracion minima (2% siempre explora algo)     |
| QLEARNING_ALPHA_MIN       | 0.02  | Alpha minimo (nunca deja de aprender del todo)   |
| QLEARNING_DECAY_PER_TRADE | 0.999 | Decaimiento de exploracion y aprendizaje         |
| QLEARNING_BACKUP_INTERVAL_HOURS | 6 | Cada cuantas horas hace backup del motor      |
| QLEARNING_AUTO_PAUSE_WINDOW     | 20 | Ventana de trades para auto-pausa             |
| QLEARNING_AUTO_PAUSE_WR_RATIO   | 0.7| Win rate minimo antes de auto-pausa           |

---

## Configuracion completa de ejemplo

```env
# Binance Futures
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_API_SECRET=tu_api_secret_aqui
BINANCE_TESTNET=false
BINANCE_LEVERAGE=25
BINANCE_MAX_MARGIN_PCT=0.95

# Servidor
PORT=8001
DRY_RUN=false

# TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123
TV_ENFORCE_IP_WHITELIST=false

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Motor de Decision
QLEARNING_ENABLED=true
QLEARNING_ALPHA_INITIAL=0.10
QLEARNING_GAMMA=0.90
QLEARNING_EPSILON_INITIAL=0.20
QLEARNING_EPSILON_MIN=0.02
QLEARNING_ALPHA_MIN=0.02
QLEARNING_DECAY_PER_TRADE=0.999
QLEARNING_BACKUP_INTERVAL_HOURS=6
QLEARNING_AUTO_PAUSE_WINDOW=20
QLEARNING_AUTO_PAUSE_WR_RATIO=0.7
```
