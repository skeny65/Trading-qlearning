# Q-Learning Strategy - bot3

## Filosofia

El agente Q-Learning aprende a filtrar y modificar senales de TradingView para
maximizar el rendimiento a largo plazo. En lugar de ejecutar ciegamente cada
alerta, el agente decide la accion optima basandose en el estado del mercado
y su experiencia acumulada.

Cada estrategia tiene su propio agente completamente aislado (Q-table, epsilon,
alpha, historial de aprendizaje). Lo que aprende la estrategia 1 no afecta a la 2
ni a ninguna otra.

---

## Estrategias y sus estados

### Estrategia 1 — TEMA 21/55 + DEMA 200 (flujo 2 alertas)

Estado 3D basado en los filtros reales del Pine Script:

| Dimension | Niveles            | Campo en params | Umbral          |
|-----------|--------------------|-----------------|-----------------|
| f1_level  | wide / mid / tight | `f1_sep`        | >=0.5% / >=0.2% |
| f2_level  | strong / mid / flat| `f2_angle`      | >=0.5% / >=0.2% |
| f3_level  | far / mid / near   | `f3_d200`       | >=1.0% / >=0.3% |

**Clave de estado:** `"wide|strong|far"` (27 combinaciones)

**Ejemplo de lo que aprende:**
- `"wide|strong|far"` → EXECUTE_FULL (tendencia fuerte, alejado de DEMA200)
- `"tight|flat|near"` → BLOQUEADO (compresion + sin impulso + pegado a DEMA200)
- `"wide|strong|near"` → SKIP (tendencia ok pero precio peligrosamente cerca de DEMA200)

**Cierre:** La señal de cierre llega desde TradingView (`signal_type: "close"`).
El Q-update ocurre **al instante** cuando llega el close, no por Price Poller.

---

### Estrategia 2 — QLearning 5D (flujo 2 alertas)

Estado 5D que captura contexto de mercado en cinco dimensiones:

| Dimension      | Valores                              | Campo en params                |
|----------------|--------------------------------------|--------------------------------|
| regime         | trend_up / trend_down / range        | `regime`                       |
| momentum       | bullish / bearish / neutral          | `momentum`                     |
| setup_type     | breakout / pullback / trend          | `setup_type`                   |
| htf_bias       | bull / bear / neutral                | `htf_bias` (acepta bullish/bearish) |
| trend_strength | extreme / strong / weak              | `trend_strength` o `adx`       |

**Clave de estado:** `"trend_up|bullish|breakout|bull|extreme"` (243 combinaciones)

**Ejemplo de lo que aprende:**
- `"trend_up|bullish|breakout|bull|extreme"` → EXECUTE_FULL (contexto ideal)
- `"trend_up|bullish|breakout|bear|weak"` → SKIP (HTF en contra)
- `"range|bearish|pullback|bear|weak"` → BLOQUEADO automaticamente

**Cierre:** Igual que estrategia 1, por alerta `signal_type: "close"`.

---

### Estrategia 3 — Tanque (flujo 1 alerta)

Estado 3D basado en la fuerza de entrada y patron de velas:

| Dimension      | Valores                        | Campo en params |
|----------------|--------------------------------|-----------------|
| entry_strength | strong / moderate / weak       | `entry_strength` |
| bar_zone       | recent / mid / old             | `bar_count`      |
| pattern        | inside_bar / breakout / pullback | `pattern`      |

**Clave de estado:** `"strong|recent|inside_bar"` (27 combinaciones)
**Cierre:** Price Poller detecta TP/SL via Binance API cada 60s.

---

### Estrategias 4-10 — Scaffold (flujo 1 alerta)

Estado 3D generico, personalizable por estrategia:

| Dimension  | Valores              | Campo en params |
|------------|----------------------|-----------------|
| price_zone | high / mid / low     | `price` (>100 / >50) |
| rr_level   | excellent / good / poor | `sl` y `tp`  |
| hour_zone  | us / asia / eu       | hora UTC actual  |

**Clave de estado:** `"high|excellent|us"` (27 combinaciones)
Editar `strategies/eN/worker.py` para personalizar `encode_state()`.
**Cierre:** Price Poller detecta TP/SL via Binance API cada 60s.

---

## Acciones — compartidas por todas las estrategias

| Accion        | Comportamiento                                           | Size multiplier |
|---------------|----------------------------------------------------------|-----------------|
| EXECUTE_FULL  | Tomar la senal con el size recibido                      | x1.0            |
| EXECUTE_HALF  | Tomar la senal con size reducido                         | x0.5            |
| SKIP          | No ejecutar — responde `skipped_by_qlearning`            | x0.0            |
| INVERT        | Ejecutar la operacion contraria con size reducido         | x0.5 opuesto    |

---

## Recompensa (r)

### Estrategias 1 y 2 (cierre por alerta):
```
r  = pnl_pct
r -= 0.05                       # comision + slippage
r -= 0.10  si duracion > 4h
r -= 0.50  si drawdown_cuenta < -10%
r += 0.20  si pnl_pct > 0 y r_multiple >= 2
```

### Estrategias 3-10 (cierre por Price Poller):
Misma formula, con `pnl_pct` calculado de `entry_price` vs precio al cierre.

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
- epsilon=0.20 → 20% de decisiones son aleatorias (exploracion inicial)
- epsilon=0.10 → 10% aleatorias, 90% basadas en lo aprendido
- epsilon=0.02 → casi no explora: confia en la Q-table acumulada

---

## Estados BLOQUEADOS y RENTABLES

| Clasificacion | Condicion   | Comportamiento                                       |
|---------------|-------------|------------------------------------------------------|
| BLOQUEADO     | Q < -0.30   | El agente evita esta accion en este contexto         |
| RENTABLE      | Q > +0.30   | El agente prefiere esta accion en este contexto      |
| Aprendiendo   | -0.30..0.30 | Datos insuficientes, sigue explorando                |

---

## INSIGHTS.md — Interfaz con el trader

Despues de cada trade cerrado, `logs/{id}/INSIGHTS.md` se regenera con:

- Tabla de estados RENTABLES con sugerencias para Pine Script
- Tabla de estados BLOQUEADOS con filtros sugeridos
- Ultimas 15 conclusiones con tags `[RENTABLE]` / `[BLOQUEADO]`
- Win rate historico y estadisticas del agente (epsilon, alpha)

Este archivo es la interfaz entre el bot y el trader humano. Leerlo permite
mejorar directamente las alertas de TradingView para que lleguen mas señales
del tipo que el agente ya sabe que son rentables.

---

## Monitoreo

```powershell
# Estado de cualquier estrategia
Invoke-WebRequest http://localhost:8001/api/strategy/1/status | Select-Object -ExpandProperty Content
Invoke-WebRequest http://localhost:8001/api/strategy/2/status | Select-Object -ExpandProperty Content

# Diario de aprendizaje
Invoke-WebRequest http://localhost:8001/api/strategy/1/journal | Select-Object -ExpandProperty Content

# INSIGHTS directos
Get-Content logs\1\INSIGHTS.md
Get-Content logs\2\INSIGHTS.md

# Posiciones pendientes (estrategias 3-10)
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content

# Todas las estrategias de un vistazo
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content
```

---

## Intervencion manual

```powershell
# Pausar agente (deja de aprender, sigue recibiendo señales)
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/pause -Method POST

# Reanudar agente
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/resume -Method POST

# Restaurar Q-Table desde backup
Copy-Item "data\strategies\1\backups\q_table_20260516_060000.json" `
          "data\strategies\1\q_table.json"

# Resetear Q-Table (tabla vacia — el agente empieza desde cero)
'{}' | Out-File data\strategies\1\q_table.json -Encoding utf8
```
