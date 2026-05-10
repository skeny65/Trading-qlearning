# Instrucciones de Setup - bot3 Multi-Strategy

## Estado actual (2026-05-09)

Sistema completamente operativo:
- 3 estrategias independientes: `apuesta`, `qlearning`, `tanque`
- Price Poller: detecta TP/SL cada 60s via Binance API publica
- Excel por estrategia: se llena automaticamente con WIN/LOSS
- bot1 es opcional: el bot aprende con o sin el

---

## Requisitos

- Python 3.10+
- Acceso a internet (Price Poller usa Binance API publica, sin key)
- Archivo `.env` configurado
- bot1 opcional (si quieres ejecutar en Alpaca)

---

## Arranque rapido

```bat
REM Doble clic:
start_bot3.bat
```

El bat hace todo automaticamente:
1. Verifica Python
2. Instala dependencias (`pip install -r requirements.txt`)
3. Verifica bot1 (aviso si no esta, no bloquea)
4. Abre ngrok en ventana separada
5. Arranca uvicorn en puerto 8001
6. Auto-restart si cae (loop 24/7)

---

## Configurar `.env`

```env
# Conexion con bot1 (opcional)
BOT1_WEBHOOK_URL=http://127.0.0.1:8000/webhook/bot3
BOT1_WEBHOOK_SECRET=a_secure_bot3_secret

# Modo
DRY_RUN=false
PORT=8001

# Secreto para alertas de TradingView
TV_WEBHOOK_SECRET=mi_secreto_webhook_123

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Verificar que todo funciona

```powershell
# 1. Health check
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content

# 2. Listar estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# 3. Test de senal manual (qlearning)
$headers = @{ "Content-Type" = "application/json"; "X-Webhook-Secret" = "mi_secreto_webhook_123" }
$body = @{
    status = "pending"; source = "tradingview"
    signal = @{
        symbol = "SOLUSDT"; action = "buy"; confidence = 0.7; size = 0.1
        params = @{
            price = 93.73; sl = 93.63; tp = 93.93; atr = 0.066; adx = 40.66
            regime = "trend_up"; momentum = "bullish"; setup_type = "breakout"
            htf_bias = "bull"; trend_strength = "extreme"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri http://localhost:8001/webhook/strategy/qlearning `
    -Method POST -Headers $headers -Body $body
```

Respuesta esperada:
```json
{"strategy": "qlearning", "status": "queued", "ql_action": "EXECUTE_FULL", ...}
```

---

## Configurar TradingView

En cada alerta de Pine Script:

- **URL Apuesta:** `https://<ngrok>.ngrok-free.app/webhook/strategy/apuesta`
- **URL QLearning:** `https://<ngrok>.ngrok-free.app/webhook/strategy/qlearning`
- **URL Tanque:** `https://<ngrok>.ngrok-free.app/webhook/strategy/tanque`
- **Header:** `X-Webhook-Secret: <TV_WEBHOOK_SECRET>`
- **Body:** JSON con el formato de `docs/webhook_format.md`

Para que el aprendizaje sea automatico, el body DEBE incluir `sl` y `tp` en `params`.

---

## Ver resultados

```powershell
# Excel de cada estrategia (llenado automaticamente con WIN/LOSS)
# Abrir con doble clic:
logs\qlearning\trade_log.xlsx
logs\apuesta\trade_log.xlsx
logs\tanque\trade_log.xlsx

# Diario de aprendizaje (actualizado tras cada trade cerrado)
Get-Content logs\qlearning\INSIGHTS.md

# Via API
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal | Select-Object -ExpandProperty Content
```

---

## Aprendizaje manual (si quieres corregir resultados)

```powershell
# Ver que se procesaria
python scripts/learn_from_excel.py --dry-run

# Procesar todas las estrategias
python scripts/learn_from_excel.py

# Solo una
python scripts/learn_from_excel.py qlearning
```

El script lee las columnas `result` (WIN/LOSS) del Excel y dispara el aprendizaje
para las filas que aun no tienen `learned_at`.

---

## Reiniciar y restaurar

```powershell
# Reiniciar bot3 (start_bot3.bat lo hace automaticamente)
taskkill /f /im python.exe

# Restaurar Q-Table desde backup
Copy-Item "data\strategies\qlearning\backups\q_table_20260509_060000.json" `
          "data\strategies\qlearning\q_table.json"

# Resetear Q-Table de una estrategia
'{}' | Out-File data\strategies\qlearning\q_table.json -Encoding utf8

# Borrar Excel para empezar de cero (bot lo recrea automaticamente)
Remove-Item logs\qlearning\trade_log.xlsx
```

---

## Cambios necesarios en bot1 (si lo usas)

**`.env` de bot1:**
```env
BOT3_WEBHOOK_SECRET=a_secure_bot3_secret
BOT3_LOCAL_ONLY=true
BOT3_ALLOWED_HOSTS=127.0.0.1,::1,localhost
```

**`core/bot_registry.py` de bot1:**
- Agregar `"bot3_qlearning"` a `KNOWN_BOTS`

Ver `docs/integration_bot1.md` para los detalles.
