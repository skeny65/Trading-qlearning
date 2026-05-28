# INSIGHTS - 1
> Actualizado: 2026-05-27 03:40 UTC | Updates totales: 2 | WR: 0.0%

---

## Estado del agente

| Parametro | Valor |
|-----------|-------|
| Epsilon (exploracion) | `0.0` |
| Alpha (aprendizaje)   | `0.0` |
| Estados en Q-table    | `5` |
| Trades ganadores      | `0` |
| Trades perdedores     | `2` |
| Win rate historico    | `0.0%` |
| Updates hoy           | `2` |

---

## Contextos RENTABLES (el agente prefiere ejecutar aqui)

_Sin datos suficientes aun. Se necesitan mas trades._

### Sugerencia para TradingView

_Pendiente de datos._

---

## Contextos BLOQUEADOS (el agente descarta automaticamente)

_Sin estados bloqueados aun. El agente necesita mas trades para identificar patrones negativos._

---

## Ultimas conclusiones

- `2026-05-27 03:40` - `tight|mid|mid` -> **EXECUTE_FULL** (reward=-0.150)  
  _Q baja de 0.000 a -0.015 tras trade perdedor (reward=-0.150). sospechoso: EXECUTE_FULL en este contexto tiende a perder._

- `2026-05-27 01:30` - `tight|strong|mid` -> **EXECUTE_FULL** (reward=-0.060)  
  _Q baja de 0.000 a -0.006 tras trade perdedor (reward=-0.060). sospechoso: EXECUTE_FULL en este contexto tiende a perder._

---

## Como usar este archivo

1. **Contextos rentables** -> busca en el Pine Script como generar mas alertas en esos contextos
2. **Contextos bloqueados** -> agrega filtros en el Pine Script para evitar esas condiciones
3. **Win rate historico** -> si sube con el tiempo, el agente esta aprendiendo correctamente
4. **Epsilon** -> cuando llega a ~0.02, el agente casi no explora: confia en lo aprendido

> Generado automaticamente por bot3. No editar manualmente.
> Archivo: `logs/1/INSIGHTS.md`