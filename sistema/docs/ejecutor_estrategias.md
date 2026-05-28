# Motor de Decision — Estrategias del Ejecutor

## Que hace el motor

El ejecutor recibe la senal de TradingView y decide si ejecutarla, reducirla, invertirla o saltarsela,
basandose en la experiencia acumulada de trades anteriores para cada contexto de mercado.

Cada estrategia tiene su motor completamente aislado. Lo que aprende la estrategia 1 no afecta a ninguna otra.

---

## Estrategias y sus estados

### Estrategia 1 — SOLUSDT / Brecha de medias + D300 (LIVE)

Estado 3D basado en indicadores Pine Script: separacion entre medias, pendiente de media verde, distancia a D300.

| Dimension       | Niveles               | Campo en params    | Umbral                    |
|-----------------|-----------------------|--------------------|---------------------------|
| brecha_level    | wide / mid / tight    | `dist_brecha`      | >=0.5% / >=0.2% / <0.2%  |
| pendiente_level | strong / mid / flat   | `pendiente_verde`  | >=0.05% / >=0.02% / <0.02%|
| d300_level      | far / mid / near      | `dist_d300`        | >=1.0% / >=0.3% / <0.3%  |

**Campos adicionales:** `sl`, `cierre_brecha`, `d300_trend`, `slope`
**Estado:** `"wide|strong|far"` (27 combinaciones)
**Cierre:** Alerta `signal_type:"close"` desde TradingView
**Ejecucion:** LIVE — SL/TP NO se colocan en Binance (TradingView gestiona el cierre)
**Nota:** Se aplica `abs()` a `pendiente_verde` para clasificar correctamente pendientes negativas.

---

### Estrategia 2 — SOLUSDT / 5D (LEARN ONLY)

Estado 5D que captura contexto de mercado en cinco dimensiones:

| Dimension      | Valores                          | Campo en params  |
|----------------|----------------------------------|------------------|
| regime         | trend_up / trend_down / range    | `regime`         |
| momentum       | bullish / bearish / neutral      | `momentum`       |
| setup_type     | breakout / pullback / trend      | `setup_type`     |
| htf_bias       | bull / bear / neutral            | `htf_bias`       |
| trend_strength | extreme / strong / weak          | `trend_strength` |

**Estado:** `"trend_up|bullish|breakout|bull|extreme"` (243 combinaciones)
**Cierre:** Alerta `signal_type:"close"` desde TradingView
**Ejecucion:** LEARN ONLY — motor aprende pero no toca Binance

---

### Estrategia 3 — SOLUSDT / Tanque (LEARN ONLY)

Estado 3D basado en fuerza de entrada y patron de velas:

| Dimension      | Valores                          | Campo en params  |
|----------------|----------------------------------|------------------|
| entry_strength | strong / moderate / weak         | `entry_strength` |
| bar_zone       | recent / mid / old               | `bar_count`      |
| pattern        | inside_bar / breakout / pullback | `pattern`        |

**Estado:** `"strong|recent|inside_bar"` (27 combinaciones)
**Cierre:** Alerta `signal_type:"close"` desde TradingView
**Ejecucion:** LEARN ONLY — motor aprende pero no toca Binance

---

### Estrategia 4 — ETHUSDT / EMA 9/21/200 (LIVE)

Estado 3D aplicado a separacion de EMAs en ETHUSDT:

| Dimension | Niveles              | Campo en params | Umbral          |
|-----------|----------------------|-----------------|-----------------|
| f1_level  | wide / mid / tight   | `f1_sep`        | >=0.5% / >=0.2% |
| f2_level  | strong / mid / flat  | `f2_angle`      | >=0.5% / >=0.2% |
| f3_level  | far / mid / near     | `f3_d200`       | >=1.0% / >=0.3% |

**Estado:** `"wide|strong|far"` (27 combinaciones)
**Cierre:** Alerta `signal_type:"close"` desde TradingView
**Ejecucion:** LIVE — SL/TP NO se colocan en Binance

---

### Estrategias 5-10 — Scaffold generico (LIVE, Price Poller)

Estado 3D generico, personalizable en `strategies/eN/worker.py`:

| Dimension  | Valores                 | Logica por defecto                 |
|------------|-------------------------|------------------------------------|
| price_zone | high / mid / low        | precio > 100 / > 50 / resto        |
| rr_level   | excellent / good / poor | rr >= 1.5 / >= 1.0 / resto         |
| hour_zone  | us / asia / eu          | UTC: 13-17 / 0-2,8-9 / resto       |

**Estado:** `"high|excellent|us"` (27 combinaciones)
**Cierre:** Price Poller detecta TP/SL via Binance API cada 60s

---

## Acciones del motor

| Accion       | Comportamiento                             | Balance usado |
|--------------|--------------------------------------------|---------------|
| EXECUTE_FULL | Ejecutar la senal con todo el balance      | 100%          |
| EXECUTE_HALF | Ejecutar con la mitad del balance          | 50%           |
| SKIP         | No ejecutar                                | 0%            |
| INVERT       | Ejecutar en direccion opuesta con la mitad | 50% opuesto   |

---

## Calculo de recompensa

```
r  = pnl_pct
r -= 0.05                        # comision + slippage estimado
r -= 0.10  si duracion > 4h
r -= 0.50  si drawdown_cuenta < -10%
r += 0.20  si pnl_pct > 0 y r_multiple >= 2
```

---

## Actualizacion del motor (Bellman)

```
Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]
```

---

## Parametros del motor

| Parametro             | Valor | Min  | Decay        |
|-----------------------|-------|------|--------------|
| alpha (aprendizaje)   | 0.10  | 0.02 | x0.999/trade |
| gamma (descuento)     | 0.90  | -    | fijo         |
| epsilon (exploracion) | 0.20  | 0.02 | x0.999/trade |

---

## Clasificacion de estados

| Clasificacion | Condicion    | Comportamiento                               |
|---------------|--------------|----------------------------------------------|
| BLOQUEADO     | Q < -0.30    | El motor evita esta accion en este contexto  |
| RENTABLE      | Q > +0.30    | El motor prefiere esta accion                |
| Aprendiendo   | -0.30..0.30  | Datos insuficientes, sigue explorando        |

---

## Monitoreo

```powershell
# Estado del motor por estrategia
Invoke-WebRequest http://localhost:8001/api/strategy/1/status | Select-Object -ExpandProperty Content

# Todas las estrategias
Invoke-WebRequest http://localhost:8001/api/strategies | Select-Object -ExpandProperty Content

# INSIGHTS
Get-Content estrategias\estrategia_1\INSIGHTS.md

# Posiciones pendientes (estrategias 5-10)
Invoke-WebRequest http://localhost:8001/pending | Select-Object -ExpandProperty Content
```

---

## Intervencion manual

```powershell
# Pausar motor de una estrategia
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/pause -Method POST

# Reanudar motor
Invoke-WebRequest -Uri http://localhost:8001/api/strategy/1/resume -Method POST

# Resetear motor (empieza desde cero)
'{}' | Out-File estrategias\estrategia_1\actividades\q_table.json -Encoding utf8

# Restaurar motor desde backup
Copy-Item "estrategias\estrategia_1\actividades\backups\q_table_20260518_060000.json" `
          "estrategias\estrategia_1\actividades\q_table.json"
```
