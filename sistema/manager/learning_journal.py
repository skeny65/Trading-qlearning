"""
learning_journal.py - Diario de aprendizaje por estrategia.

Despues de cada Q-update registra:
  - Que cambio (estado, accion, reward, Q anterior vs nuevo)
  - Una conclusion en texto plano (legible por humanos)
  - Si el estado se volvio "bloqueado" (Q negativa consistente)

Genera dos tipos de artefactos:
  logs/{strategy_id}/learning_journal.jsonl   -- registro maquina (una linea por update)
  logs/{strategy_id}/insights/YYYY-MM-DD.md   -- resumen diario legible

El objetivo es que el usuario pueda leer las conclusiones y mejorar
directamente la estrategia de TradingView basandose en lo que el agente aprendio.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("bot3.journal")

BLOCK_THRESHOLD = -0.30   # Q-value por debajo del cual consideramos "bloqueado"
GOOD_THRESHOLD  =  0.30   # Q-value por encima del cual consideramos "rentable"


class LearningJournal:
    """Registra y analiza el aprendizaje del agente para una estrategia."""

    def __init__(self, strategy_id: str):
        self.strategy_id    = strategy_id
        self._log_dir       = Path(config.strategy_actividades_dir(strategy_id))
        self._journal_path  = self._log_dir / "learning_journal.jsonl"
        self._insights_path = Path(config.strategy_data_dir(strategy_id)) / "INSIGHTS.md"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Registro por trade
    # -------------------------------------------------------------------------

    def record_update(
        self,
        state:      str,
        action:     str,
        reward:     float,
        old_q:      float,
        new_q:      float,
        q_table:    dict,
        trade_meta: Optional[dict] = None,
    ) ->dict:
        """
        Registra un Q-update y genera la conclusion automatica.
        Llama a este metodo desde StrategyWorker.update_q().

        Retorna la entrada del journal (util para la API).
        """
        conclusion = self._make_conclusion(state, action, reward, old_q, new_q, q_table)
        blocked    = new_q < BLOCK_THRESHOLD
        good       = new_q > GOOD_THRESHOLD

        entry = {
            "ts":           datetime.now(timezone.utc).isoformat(),
            "strategy_id":  self.strategy_id,
            "state":        state,
            "action":       action,
            "reward":       round(reward,  4),
            "old_q":        round(old_q,   6),
            "new_q":        round(new_q,   6),
            "delta_q":      round(new_q - old_q, 6),
            "blocked":      blocked,
            "good":         good,
            "conclusion":   conclusion,
            "trade_meta":   trade_meta or {},
        }

        self._append_to_journal(entry)

        status = "BLOQUEADO" if blocked else ("RENTABLE" if good else "aprendiendo")
        logger.info(
            f"[{self.strategy_id}] Journal [{status}] {state} ->{action}: "
            f"reward={reward:+.3f} Q: {old_q:.3f} ->{new_q:.3f} | {conclusion}"
        )

        # Regenerar INSIGHTS.md con el estado actual del aprendizaje
        self._refresh_insights(q_table, entry)

        return entry

    # -------------------------------------------------------------------------
    # INSIGHTS.md - archivo unico por estrategia, siempre actualizado
    # -------------------------------------------------------------------------

    def generate_insights_file(self, q_table: dict, agent_stats: dict) ->str:
        """
        Genera/sobreescribe logs/{strategy_id}/INSIGHTS.md con el estado
        actual del aprendizaje. Un solo archivo por estrategia.

        Se llama automaticamente despues de cada Q-update y desde la API.
        """
        now            = datetime.now(timezone.utc)
        today          = now.strftime("%Y-%m-%d")
        updated_at     = now.strftime("%Y-%m-%d %H:%M UTC")

        best_states    = self._top_states(q_table, top=5, highest=True,  min_q=0.0)
        blocked_states = self._top_states(q_table, top=5, highest=False, max_q=BLOCK_THRESHOLD)
        all_entries    = self.get_recent(500)
        today_entries  = [e for e in all_entries if e.get("ts", "").startswith(today)]
        total_updates  = len(all_entries)
        wins           = sum(1 for e in all_entries if e.get("reward", 0) > 0)
        losses         = sum(1 for e in all_entries if e.get("reward", 0) < 0)
        win_rate       = round(wins / total_updates * 100, 1) if total_updates else 0.0

        lines = [
            f"# INSIGHTS - {self.strategy_id.upper()}",
            f"> Actualizado: {updated_at} | Updates totales: {total_updates} | WR: {win_rate}%",
            "",
            "---",
            "",
            "## Estado del agente",
            "",
            f"| Parametro | Valor |",
            f"|-----------|-------|",
            f"| Epsilon (exploracion) | `{round(agent_stats.get('epsilon', 0), 4)}` |",
            f"| Alpha (aprendizaje)   | `{round(agent_stats.get('alpha', 0), 4)}` |",
            f"| Estados en Q-table    | `{len(q_table)}` |",
            f"| Trades ganadores      | `{wins}` |",
            f"| Trades perdedores     | `{losses}` |",
            f"| Win rate historico    | `{win_rate}%` |",
            f"| Updates hoy           | `{len(today_entries)}` |",
            "",
            "---",
            "",
            "## Contextos RENTABLES (el agente prefiere ejecutar aqui)",
            "",
        ]

        if best_states:
            lines += [
                "| Estado | Accion | Q-value | Lo que aprendio |",
                "|--------|--------|---------|-----------------|",
            ]
            for s, a, q in best_states:
                lines.append(f"| `{s}` | **{a}** | `{q:+.4f}` | {self._interpret_state(s, a, q)} |")
        else:
            lines.append("_Sin datos suficientes aun. Se necesitan mas trades._")

        lines += [
            "",
            "### Sugerencia para TradingView",
            "",
        ]
        if best_states:
            parts = best_states[0][0].split("|")
            lines.append(
                f"Los mejores resultados ocurren cuando el mercado esta en: "
                f"**{' + '.join(parts)}**. Considera priorizar alertas en este contexto."
            )
        else:
            lines.append("_Pendiente de datos._")

        lines += [
            "",
            "---",
            "",
            "## Contextos BLOQUEADOS (el agente descarta automaticamente)",
            "",
        ]

        if blocked_states:
            lines += [
                "| Estado | Accion evitada | Q-value | Por que falla |",
                "|--------|----------------|---------|---------------|",
            ]
            for s, a, q in blocked_states:
                lines.append(f"| `{s}` | ~~{a}~~ | `{q:+.4f}` | {self._interpret_state(s, a, q)} |")

            lines += [
                "",
                "### Filtros sugeridos para TradingView / Pine Script",
                "",
            ]
            for s, a, q in blocked_states:
                parts = s.split("|")
                lines.append(f"- Evitar entradas cuando: **{' + '.join(parts)}** (historial negativo, Q={q:+.4f})")
        else:
            lines.append("_Sin estados bloqueados aun. El agente necesita mas trades para identificar patrones negativos._")

        lines += [
            "",
            "---",
            "",
            "## Ultimas conclusiones",
            "",
        ]

        recent = all_entries[-15:]
        if recent:
            for e in reversed(recent):
                ts_short = e["ts"][11:16]
                tag      = " `[BLOQUEADO]`" if e.get("blocked") else (" `[RENTABLE]`" if e.get("good") else "")
                lines.append(
                    f"- `{e['ts'][:10]} {ts_short}` - `{e['state']}` -> **{e['action']}**"
                    f" (reward={e['reward']:+.3f}){tag}  \n"
                    f"  _{e['conclusion']}_"
                )
                lines.append("")
        else:
            lines.append("_Sin conclusiones aun._")

        lines += [
            "---",
            "",
            "## Como usar este archivo",
            "",
            "1. **Contextos rentables** -> busca en el Pine Script como generar mas alertas en esos contextos",
            "2. **Contextos bloqueados** -> agrega filtros en el Pine Script para evitar esas condiciones",
            "3. **Win rate historico** -> si sube con el tiempo, el agente esta aprendiendo correctamente",
            "4. **Epsilon** -> cuando llega a ~0.02, el agente casi no explora: confia en lo aprendido",
            "",
            f"> Generado automaticamente por bot3. No editar manualmente.",
            f"> Archivo: `logs/{self.strategy_id}/INSIGHTS.md`",
        ]

        content = "\n".join(lines)
        try:
            self._insights_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Error escribiendo INSIGHTS.md: {e}")

        return content

    def _refresh_insights(self, q_table: dict, last_entry: dict):
        """Regenera INSIGHTS.md silenciosamente tras cada Q-update."""
        try:
            # Obtener stats del agente desde la ultima entrada
            agent_stats = {
                "epsilon": last_entry.get("trade_meta", {}).get("epsilon", 0.0),
                "alpha":   last_entry.get("trade_meta", {}).get("alpha",   0.0),
            }
            self.generate_insights_file(q_table, agent_stats)
        except Exception as e:
            logger.warning(f"[{self.strategy_id}] No se pudo refrescar INSIGHTS.md: {e}")

    # backward-compat alias
    def generate_daily_report(self, q_table: dict, agent_stats: dict) ->str:
        return self.generate_insights_file(q_table, agent_stats)

    # -------------------------------------------------------------------------
    # API: leer journal
    # -------------------------------------------------------------------------

    def get_recent(self, n: int = 20) ->list:
        """Retorna las ultimas N entradas del journal."""
        entries = []
        if not self._journal_path.exists():
            return entries
        try:
            with open(self._journal_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.error(f"Error leyendo journal: {e}")
        return entries[-n:]

    def get_summary(self, q_table: dict) ->dict:
        """Resumen rapido para el endpoint /api/strategy/{id}/journal."""
        entries        = self.get_recent(100)
        blocked_states = self._top_states(q_table, top=3, highest=False)
        best_states    = self._top_states(q_table, top=3, highest=True)

        return {
            "strategy_id":    self.strategy_id,
            "total_updates":  len(entries),
            "blocked_states": [
                {"state": s, "action": a, "q": q, "interp": self._interpret_state(s, a, q)}
                for s, a, q in blocked_states
            ],
            "best_states": [
                {"state": s, "action": a, "q": q, "interp": self._interpret_state(s, a, q)}
                for s, a, q in best_states
            ],
            "recent_conclusions": [
                {"ts": e["ts"], "state": e["state"], "action": e["action"],
                 "reward": e["reward"], "conclusion": e["conclusion"],
                 "blocked": e.get("blocked", False), "good": e.get("good", False)}
                for e in entries[-5:]
            ],
        }

    # -------------------------------------------------------------------------
    # Privados
    # -------------------------------------------------------------------------

    def _append_to_journal(self, entry: dict):
        try:
            with open(self._journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error escribiendo journal: {e}")

    def _read_today_entries(self, today: str) ->list:
        entries = self.get_recent(500)
        return [e for e in entries if e.get("ts", "").startswith(today)]

    def _top_states(
        self,
        q_table:  dict,
        top:      int   = 5,
        highest:  bool  = True,
        min_q:    float = None,
        max_q:    float = None,
    ) ->list:
        """
        Retorna los (state, action, q) mas altos o mas bajos de la Q-table.
        min_q / max_q filtran por umbral (e.g. solo positivos o solo muy negativos).
        """
        pairs = []
        for state, actions in q_table.items():
            for action, q in actions.items():
                if q == 0.0:
                    continue
                if min_q is not None and q < min_q:
                    continue
                if max_q is not None and q > max_q:
                    continue
                pairs.append((state, action, round(q, 6)))

        pairs.sort(key=lambda x: x[2], reverse=highest)
        return pairs[:top]

    def _make_conclusion(
        self,
        state:  str,
        action: str,
        reward: float,
        old_q:  float,
        new_q:  float,
        q_table: dict,
    ) ->str:
        """Genera una conclusion en texto plano a partir de un Q-update."""
        direction = "sube" if new_q > old_q else "baja"
        won       = reward > 0

        # Que tan bloqueado/rentable esta el estado ahora
        if new_q < BLOCK_THRESHOLD:
            sentiment = f"BLOQUEADO: agente evitara {action} en este contexto"
        elif new_q > GOOD_THRESHOLD:
            sentiment = f"RENTABLE: agente preferira {action} en este contexto"
        elif new_q < 0:
            sentiment = f"sospechoso: {action} en este contexto tiende a perder"
        else:
            sentiment = f"aprendiendo: datos insuficientes aun"

        result_text = f"trade {'ganador' if won else 'perdedor'} (reward={reward:+.3f})"
        return f"Q {direction} de {old_q:.3f} a {new_q:.3f} tras {result_text}. {sentiment}."

    def _interpret_state(self, state: str, action: str, q: float) ->str:
        """Traduce un estado codificado a una frase legible."""
        parts = state.split("|")

        if q > GOOD_THRESHOLD:
            verdict = "Ejecutar con confianza"
        elif q < BLOCK_THRESHOLD:
            verdict = "Evitar - historial negativo"
        else:
            verdict = "Neutral - pocos datos"

        context = " + ".join(parts) if parts else state
        return f"{context} ->{verdict}"
