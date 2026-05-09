# Q-Learning Strategy - bot3

## Filosofia

El agente Q-Learning aprende a filtrar y modificar senales de TradingView para
maximizar el rendimiento a largo plazo. En lugar de ejecutar ciegamente cada
alerta, el agente decide la accion optima basandose en el estado del mercado
y su experiencia acumulada.

Cada estrategia tiene su propio agente completamente aislado (Q-table, epsilon,
alpha, historial de aprendizaje). Lo que aprende "qlearning" no afecta a "apuesta"
ni a "tanque".

---

## Estrategias disponibles

### `qlearning` — Estado 5D (243 combinaciones)

La estrategia mas rica. Captura el contexto del mercado en cinco dimensiones.

| Dimension      | Valores                              | Origen en params               |
|----------------|--------------------------------------|--------------------------------|
| regime         | trend_up \| trend_down \| range      | campo `regime`                 |
| momentum       | bullish \| bearish \| neutral        | campo `momentum`               |
| setup_type     | breakout \| pullback \| trend        | campo `setup_type`             |
| htf_bias       | bull \| bear \| neutral              | campo `htf_bias`               |
| trend_strength | extreme \| strong \| weak            | campo `trend_strength` o `adx` |

**Clave de estado:** `"trend_up|bullish|breakout|bull|extreme"`

**Ejemplo de lo que aprende:**
- `"trend_up|bullish|breakout|bull|extreme"` -> EXECUTE_FULL (contexto ideal)
- `"trend_up|bullish|breakout|bear|weak"` -> SKIP (contra-tendencia HTF)
- `"range|bearish|pullback|bear|weak"` -> BLOQUEADO automaticamente

### `apuesta` — Estado 3D (precio, R:R, hora)

| Dimension  | Valores                         | Origen                            |
|------------|---------------------------------|-----------------------------------|
| price_zone | high \| mid \| low              | precio relativo al rango del dia  |
| rr_level   | good \| ok \| poor              | ratio riesgo/beneficio (sl/tp)    |
| hour_zone  | london \| ny \| asia \| off     | hora UTC de la senal              |

### `tanque` — Estado 3D (fuerza, zona, patron)

| Dimension       | Valores                         |
|-----------------|---------------------------------|
| entry_strength  | strong \| medium \| weak        |
| bar_zone        | upper \| mid \| lower           |
| pattern         | engulfing \| doji \| momentum   |

---

## Acciones (a) — compartidas por todas las estrategias

| Accion        | Comportamiento                                          | Multiplicador |
|---------------|---------------------------------------------------------|---------------|
| EXECUTE_FULL  | Tomar la senal con el size recibido                     | x1.0          |
| EXECUTE_HALF  | Tomar la senal con size reducido                        | x0.5          |
| SKIP          | No ejecutar - responde `skipped_by_qlearning`           | x0.0          |
| INVERT        | Ejecutar la operacion contraria con size reducido        | x0.5 opuesto  |

---

## Recompensa (r) — automatica via Price Poller

El Price Poller (Binance API) detecta TP/SL y calcula la recompensa:

```
TP HIT  -> reward = +0.40  (trade ganador basico)
SL HIT  -> reward = -0.40  (trade perdedor basico)
EXPIRED -> reward =  0.00  (> 24h sin cierre)
```

Para aprendizaje manual (`/api/strategy/{id}/update`):
```
r  = pnl_pct
r -= 0.05                       # comision + slippage
r -= 0.10  si duracion > 4h
r -= 0.50  si drawdown_cuenta < -10%
r += 0.20  si pnl_pct > 0 y r_multiple >= 2
```

---

## Actualizacion Q-Table (Bellman)

```
Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]
```

---

## Hiperparametros iniciales

| Parametro            | Valor | Min  | Decay         |
|----------------------|-------|------|---------------|
| alpha (aprendizaje)  | 0.10  | 0.02 | x0.999/trade  |
| gamma (descuento)    | 0.90  | -    | fijo          |
| epsilon (exploracion)| 0.20  | 0.02 | x0.999/trade  |

**Interpretacion de epsilon:**
- epsilon=0.20 -> 20% de decisiones son aleatorias (exploracion)
- epsilon=0.10 -> 10% aleatorias, 90% basadas en lo aprendido
- epsilon=0.02 -> casi no explora: confia en la Q-table

---

## Estados BLOQUEADOS y RENTABLES

El agente clasifica automaticamente cada estado:

| Clasificacion | Condicion  | Comportamiento                                          |
|---------------|------------|---------------------------------------------------------|
| BLOQUEADO     | Q < -0.30  | El agente evita esta accion en este contexto            |
| RENTABLE      | Q > +0.30  | El agente prefiere esta accion en este contexto         |
| Aprendiendo   | -0.30..0.30| Datos insuficientes, sigue explorando                   |

Cuando un estado llega a BLOQUEADO, el agente lo esquivara automaticamente
(la accion con Q negativa nunca sera elegida por epsilon-greedy si hay
alternativas con Q >= 0).

---

## Diario de aprendizaje (INSIGHTS.md)

Despues de cada trade, el agente genera/actualiza `logs/{id}/INSIGHTS.md`:

- Tabla de estados RENTABLES con sugerencias para Pine Script
- Tabla de estados BLOQUEADOS con filtros sugeridos
- Ultimas 15 conclusiones con tags `[RENTABLE]` / `[BLOQUEADO]`
- Win rate historico y estadisticas del agente

Este archivo es la interfaz entre el bot y el trader humano. Leerlo permite
mejorar directamente las alertas de TradingView.

---

## Monitoreo

```powershell
# Estado del agente qlearning
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/status | Select-Object -ExpandProperty Content

# Resumen del diario de aprendizaje
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal | Select-Object -ExpandProperty Content

# Ultimas entradas del journal
Invoke-WebRequest http://localhost:8001/api/strategy/qlearning/journal/recent | Select-Object -ExpandProperty Content

# Leer INSIGHTS.md directamente
Get-Content logs\qlearning\INSIGHTS.md

# Posiciones pendientes monitoreadas por Price Poller
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

---

## Intervencion manual

```powershell
# Pausar agente
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/pause -Method POST

# Reanudar agente
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/qlearning/resume -Method POST

# Restaurar Q-Table desde backup
Copy-Item "data\strategies\qlearning\backups\q_table_20260508_060000.json" `
          "data\strategies\qlearning\q_table.json"

# Resetear Q-Table (tabla vacia)
'{}' | Out-File data\strategies\qlearning\q_table.json -Encoding utf8
```
