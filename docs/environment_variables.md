# Variables de Entorno

Copia `.env.example` a `.env` y rellena los valores.

## Variables originales (heredadas de bot1)

| Variable              | Descripcion                                    | Ejemplo               |
|-----------------------|------------------------------------------------|-----------------------|
| ALPACA_API_KEY        | API key de Alpaca                              | PKxxx...              |
| ALPACA_SECRET_KEY     | Secret key de Alpaca                           | xxx...                |
| ALPACA_BASE_URL       | URL base del API de Alpaca                     | https://paper-api...  |
| WEBHOOK_SECRET        | Secreto para el webhook de Claude Routines     | changeme123           |
| TELEGRAM_BOT_TOKEN    | Token del bot de Telegram                      | 123456:AABBcc...      |
| TELEGRAM_CHAT_ID      | Chat ID de Telegram                            | -100123456789         |
| DRY_RUN               | true = no ejecuta ordenes reales               | true                  |
| PORT                  | Puerto del servidor FastAPI                    | 8001                  |

## Variables nuevas - TradingView Webhook

| Variable                  | Descripcion                                                  | Default  |
|---------------------------|--------------------------------------------------------------|----------|
| TV_WEBHOOK_SECRET         | Secreto para el header X-Webhook-Secret (distinto al otro)  | -        |
| TV_ALLOWED_IPS            | IPs de TradingView separadas por coma                        | (ver abajo) |
| TV_ENFORCE_IP_WHITELIST   | Validar IP de origen                                         | false    |

IPs oficiales de TradingView (2026): `52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7`

## Variables nuevas - Q-Learning

| Variable                      | Descripcion                                           | Default |
|-------------------------------|-------------------------------------------------------|---------|
| QLEARNING_ENABLED             | Activar el agente Q-Learning                          | true    |
| QLEARNING_ALPHA_INITIAL       | Learning rate inicial                                 | 0.10    |
| QLEARNING_ALPHA_MIN           | Learning rate minimo (floor del decay)                | 0.02    |
| QLEARNING_GAMMA               | Factor de descuento (horizonte temporal)              | 0.90    |
| QLEARNING_EPSILON_INITIAL     | Exploracion inicial (0=explotar, 1=explorar)          | 0.20    |
| QLEARNING_EPSILON_MIN         | Epsilon minimo (floor del decay)                      | 0.02    |
| QLEARNING_DECAY_PER_TRADE     | Multiplicador de decay por trade                      | 0.999   |
| QLEARNING_BACKUP_INTERVAL_HOURS | Cada cuantas horas crear backup de Q-Table          | 6       |
| QLEARNING_AUTO_PAUSE_WINDOW   | Numero de trades para evaluar degradacion             | 20      |
| QLEARNING_AUTO_PAUSE_WR_RATIO | Ratio de caida de win rate para auto-pausa            | 0.7     |
| QLEARNING_AUTO_PAUSE_DD_RATIO | Ratio de drawdown para auto-pausa                     | 1.5     |
