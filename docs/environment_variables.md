# Variables de Entorno — bot3-qlearning

Copia `.env.example` a `.env` y edita los valores marcados con *.

---

## Conexion con bot1

| Variable            | Descripcion                                              | Valor actual          |
|---------------------|----------------------------------------------------------|-----------------------|
| `BOT1_WEBHOOK_URL`  | URL del endpoint de bot1 que recibe señales de bot3      | `http://127.0.0.1:8000/webhook/bot3` |
| `BOT1_WEBHOOK_SECRET` * | Secreto que bot1 espera en `X-Webhook-Secret`        | `a_secure_bot3_secret` (cambiar en prod) |

> Este secreto es el mismo que `BOT3_WEBHOOK_SECRET` en el `.env` de bot1.

---

## Servidor bot3

| Variable  | Descripcion                               | Default |
|-----------|-------------------------------------------|---------|
| `PORT`    | Puerto donde escucha uvicorn              | `8001`  |
| `DRY_RUN` | `true` = no envia a bot1, solo loguea     | `false` |

---

## TradingView Webhook

| Variable                  | Descripcion                                                    | Default |
|---------------------------|----------------------------------------------------------------|---------|
| `TV_WEBHOOK_SECRET` *     | Clave que TradingView envia en `X-Webhook-Secret`              | —       |
| `TV_ALLOWED_IPS`          | IPs oficiales de TradingView (separadas por coma)              | ver abajo |
| `TV_ENFORCE_IP_WHITELIST` | `true` = rechaza peticiones de IPs no permitidas               | `false` |

IPs oficiales TradingView (2026):
```
52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7
```

> Dejar `TV_ENFORCE_IP_WHITELIST=false` mientras se usa ngrok o se prueba localmente.

---

## Telegram (opcional)

| Variable             | Descripcion                          | Default |
|----------------------|--------------------------------------|---------|
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram            | —       |
| `TELEGRAM_CHAT_ID`   | Chat ID donde llegan las alertas     | —       |

Si estas variables estan vacias, bot3 simplemente no envia notificaciones (no hay error).

---

## Q-Learning — hiperparametros

| Variable                        | Descripcion                                        | Default |
|---------------------------------|----------------------------------------------------|---------|
| `QLEARNING_ENABLED`             | Activar el agente Q-Learning                       | `true`  |
| `QLEARNING_ALPHA_INITIAL`       | Learning rate inicial                              | `0.10`  |
| `QLEARNING_ALPHA_MIN`           | Learning rate minimo (floor del decay)             | `0.02`  |
| `QLEARNING_GAMMA`               | Factor de descuento (horizonte temporal)           | `0.90`  |
| `QLEARNING_EPSILON_INITIAL`     | Exploracion inicial (0=explotar, 1=explorar)       | `0.20`  |
| `QLEARNING_EPSILON_MIN`         | Epsilon minimo (floor del decay)                   | `0.02`  |
| `QLEARNING_DECAY_PER_TRADE`     | Multiplicador de decay por trade                   | `0.999` |
| `QLEARNING_BACKUP_INTERVAL_HOURS` | Cada cuantas horas crear backup de Q-Table       | `6`     |
| `QLEARNING_AUTO_PAUSE_WINDOW`   | Trades para evaluar degradacion                    | `20`    |
| `QLEARNING_AUTO_PAUSE_WR_RATIO` | Ratio de caida de win rate para auto-pausa         | `0.7`   |

---

## Variables que bot3 NO usa

Bot3 no conecta directamente con Alpaca — toda ejecucion pasa por bot1.
Por eso el `.env` de bot3 **no tiene** `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` ni `ALPACA_BASE_URL`.

---

## Variables en el `.env` de bot1 (referencia)

Estos valores van en bot1, no en bot3:

```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```
