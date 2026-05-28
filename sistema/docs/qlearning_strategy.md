# Q-Learning Strategy - bot3

## Filosofia

El agente Q-Learning aprende a filtrar y modificar senales de TradingView para
maximizar el rendimiento a largo plazo. En lugar de ejecutar ciegamente cada
alerta, el agente decide la accion optima basandose en el estado del mercado
y su experiencia acumulada.

Cada estrategia tiene su propio agente completamente aislado (Q-table, epsilon,
alpha, historial de aprendizaje). Lo que aprende la estrategia 1 no afecta a
ninguna otra.

---

## Estrategias y sus estados

### Estrategia 1 — SOLUSDT / Brecha de medias + D300 (LIVE)

Estado 3D basado en indicadores de Pine Script: separacion entre medias, pendiente de media verde, y distancia a D300.

| Dimension      | Niveles               | Campo en params    | Umbral                   |
|----------------|-----------------------|--------------------|--------------------------|
| brecha_level   | wide / mid / tight    | `dist_brecha`      | >=0.5% / >=0.2% / <0.2%  |
| pendiente_level| strong / mid / flat   | `pendiente_verde`  | >=0.05% / >=0.02% / <0.02%|
| d300_level     | far / mid / near      | `dist_d300`        | >=1.0% / >=0.3% / <0.3%  |

**Campos adicionales recibidos:** `sl` (stop loss), `cierre_brecha`, `d300_trend`, `slope`
**Clave de estado:** `"wide|strong|far"` (27 combinaciones)
**Cierre:** Alerta `signal_type: "close"` desde TradingView (inmediato)
**close_reason posibles:** `"Cruce contrario"` | `"Stop Loss"`
**Ejecucion:** LIVE — ordenes reales en Binance Futures. **SL/TP NO se colocan en Binance** — TradingView gestiona el cierre via alerta explícita.
**Nota pendiente_verde:** Se aplica `abs()` al valor para clasificar correctamente tanto pendientes alcistas como bajistas como "strong" (>=0.05%).

---

### Estrategia 2 — SOLUSDT / QLearning 5D (LEARN ONLY)

Estado 5D que captura contexto de mercado en cinco dimensiones:

| Dimension      | Valores                          | Campo en params  |
|----------------|----------------------------------|------------------|
| regime         | trend_up / trend_down / range    | `regime`         |
| momentum       | bullish / bearish / neutral      | `momentum`       |
| setup_type     | breakout / pullback / trend      | `setup_type`     |
| htf_bias       | bull / bear / neutral            | `htf_bias`       |
| trend_strength | extreme / strong / weak          | `trend_strength` |

**Clave de estado:** `"trend_up|bullish|breakout|bull|extreme"` (243 combinaciones)
**Cierre:** Alerta `signal_type: "close"` desde TradingView (inmediato)
**Ejecucion:** LEARN ONLY — aprende sin tocar Binance

---

### Estrategia 3 — SOLUSDT / Tanque (LEARN ONLY)

Estado 3D basado en la fuerza de entrada y patron de velas:

| Dimension      | Valores                          | Campo en params  |
|----------------|----------------------------------|------------------|
| entry_strength | strong / moderate / weak         | `entry_strength` |
| bar_zone       | recent / mid / old               | `bar_count`      |
| pattern        | inside_bar / breakout / pullback | `pattern`        |

**Clave de estado:** `"strong|recent|inside_bar"` (27 combinaciones)
**Cierre:** Alerta `signal_type: "close"` desde TradingView (inmediato)
**Ejecucion:** LEARN ONLY — aprende sin tocar Binance

---

### Estrategia 4 — ETHUSDT / EMA 9/21/200 (LIVE)

Estado 3D identico a la estrategia 1, aplicado a EMA 9/21/200 en ETHUSDT:

| Dimension | Niveles              | Campo en params | Umbral           |
|-----------|----------------------|-----------------|------------------|
| f1_level  | wide / mid / tight   | `f1_sep`        | >=0.5% / >=0.2%  |
| f2_level  | strong / mid / flat  | `f2_angle`      | >=0.5% / >=0.2%  |
| f3_level  | far / mid / near     | `f3_d200`       | >=1.0% / >=0.3%  |

**Clave de estado:** `"wide|strong|far"` (27 combinaciones)
**Soporta:** largos (`buy`) y cortos (`sell`) con 4 variantes de alerta
**Cierre:** Alerta `signal_type: "close"` desde TradingView (inmediato)
**close_reason:** siempre `"strategy_exit"` (TradingView gestiona SL/TP/trailing internamente)
**Ejecucion:** LIVE — ordenes reales en Binance Futures

---

### Estrategias 5-10 — Scaffold generico (LIVE, Price Poller)

Estado 3D generico, personalizable por estrategia editando `strategies/eN/worker.py`:

| Dimension  | Valores                 | Logica por defecto              |
|------------|-------------------------|---------------------------------|
| price_zone | high / mid / low        | precio > 100 / > 50 / resto     |
| rr_level   | excellent / good / poor | rr >= 1.5 / >= 1.0 / resto      |
| hour_zone  | us / asia / eu          | hora UTC: 13-17 / 0-2,8-9 / resto |

**Clave de estado:** `"high|excellent|us"` (27 combinaciones)
**Cierre:** Price Poller detecta TP/SL via Binance API cada 60s

---

## Acciones — compartidas por todas las estrategias

| Accion       | Comportamiento                                  | Efecto en balance |
|--------------|-------------------------------------------------|-------------------|
| EXECUTE_FULL | Ejecutar la senal con todo el balance disponible | 100%             |
| EXECUTE_HALF | Ejecutar con la mitad del balance               | 50%               |
| SKIP         | No ejecutar                                     | 0%                |
| INVERT       | Ejecutar en direccion opuesta con mitad         | 50% opuesto       |

---

## Recompensa (r)

```
r  = pnl_pct
r -= 0.05                        # comision + slippage estimado
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

---

## Estados BLOQUEADOS y RENTABLES

| Clasificacion | Condicion   | Comportamiento                                  |
|---------------|-------------|-------------------------------------------------|
| BLOQUEADO     | Q < -0.30   | El agente evita esta accion en este contexto    |
| RENTABLE      | Q > +0.30   | El agente prefiere esta accion en este contexto |
| Aprendiendo   | -0.30..0.30 | Datos insuficientes, sigue explorando           |

---

## Monitoreo

```powershell
# Estado de cualquier estrategia
Invoke-WebRequest http://localhost:8001/api/strategy/1/status | Select-Object -ExpandProperty Content

# Todas las estrategias de un vistazo
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# INSIGHTS directos
Get-Content logs\1\INSIGHTS.md
Get-Content logs\4\INSIGHTS.md

# Posiciones pendientes (estrategias 5-10)
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

---

## Intervencion manual

```powershell
# Pausar agente
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/pause -Method POST

# Reanudar agente
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/resume -Method POST

# Resetear Q-Table (empieza desde cero)
'{}' | Out-File data\strategies\1\q_table.json -Encoding utf8

# Restaurar Q-Table desde backup
Copy-Item "data\strategies\1\backups\q_table_20260518_060000.json" "data\strategies\1\q_table.json"
```
