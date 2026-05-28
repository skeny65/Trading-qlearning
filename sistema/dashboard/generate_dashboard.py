"""
Dashboard generator - produces an HTML report for the trading bot.
Includes a Q-Learning Insights section.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("bot3.dashboard")

QTABLE_PATH = "data/qlearning/q_table.json"
STATS_PATH  = "data/qlearning/qlearning_stats.json"
OUTPUT_DIR  = "dashboard/output"
ACTIONS     = ["EXECUTE_FULL", "EXECUTE_HALF", "SKIP", "INVERT"]


def _load_json(path: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _build_qlearning_section(q_table: dict, stats: dict) -> str:
    """Build the Q-Learning HTML section with Plotly heatmap."""
    if not q_table:
        return "<p>No Q-table data yet. Run some trades first.</p>"

    states  = sorted(q_table.keys())
    actions = ACTIONS

    # Build heatmap data
    z_rows  = []
    for action in actions:
        row = [round(q_table[s].get(action, 0.0), 4) for s in states]
        z_rows.append(row)

    z_json      = json.dumps(z_rows)
    states_json = json.dumps(states)
    actions_json = json.dumps(actions)

    alpha   = round(stats.get("alpha",   0.0), 6)
    epsilon = round(stats.get("epsilon", 0.0), 6)
    paused  = stats.get("paused", False)

    # Count best action per state
    action_counts = {a: 0 for a in ACTIONS}
    best_pairs    = []
    worst_pairs   = []

    for state, qvals in q_table.items():
        best_a = max(qvals, key=qvals.get)
        action_counts[best_a] += 1

    all_pairs = [
        (state, action, q_table[state][action])
        for state in q_table
        for action in q_table[state]
    ]
    all_pairs.sort(key=lambda x: x[2], reverse=True)
    best_pairs  = all_pairs[:3]
    worst_pairs = all_pairs[-3:]

    best_html  = "".join(f"<li><code>{s}|{a}</code> = {v:.4f}</li>" for s,a,v in best_pairs)
    worst_html = "".join(f"<li><code>{s}|{a}</code> = {v:.4f}</li>" for s,a,v in worst_pairs)
    count_html = "".join(
        f"<li><b>{a}</b>: {action_counts[a]} estados</li>" for a in ACTIONS
    )

    paused_badge = (
        '<span class="badge bg-danger">PAUSADO</span>'
        if paused else
        '<span class="badge bg-success">ACTIVO</span>'
    )

    return f"""
<div class="card mb-4">
  <div class="card-header d-flex justify-content-between align-items-center">
    <h5 class="mb-0">&#129504; Q-Learning Insights</h5>
    {paused_badge}
  </div>
  <div class="card-body">
    <div class="row mb-3">
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">Alpha (learning rate)</span>
          <span class="stat-value">{alpha}</span>
        </div>
      </div>
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">Epsilon (exploration)</span>
          <span class="stat-value">{epsilon}</span>
        </div>
      </div>
      <div class="col-md-4">
        <div class="stat-box">
          <span class="stat-label">States discovered</span>
          <span class="stat-value">{len(q_table)} / 27</span>
        </div>
      </div>
    </div>

    <div id="qheatmap" style="height:350px;"></div>

    <div class="row mt-3">
      <div class="col-md-4">
        <h6>&#127881; Best state-actions</h6>
        <ul>{best_html}</ul>
      </div>
      <div class="col-md-4">
        <h6>&#128308; Worst state-actions</h6>
        <ul>{worst_html}</ul>
      </div>
      <div class="col-md-4">
        <h6>&#128200; Preferred action per state</h6>
        <ul>{count_html}</ul>
      </div>
    </div>
  </div>
</div>

<script>
(function() {{
  var z       = {z_json};
  var xLabels = {states_json};
  var yLabels = {actions_json};
  var trace = {{
    z:    z,
    x:    xLabels,
    y:    yLabels,
    type: 'heatmap',
    colorscale: 'RdYlGn',
    showscale: true,
  }};
  var layout = {{
    title:  'Q-Table heatmap (action x state)',
    margin: {{l:120, r:20, t:40, b:120}},
    xaxis:  {{tickangle: -45, tickfont: {{size: 10}}}},
  }};
  Plotly.newPlot('qheatmap', [trace], layout, {{responsive: true}});
}})();
</script>
"""


def generate(output_path: str = None):
    """Generate dashboard HTML file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts          = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"dashboard_{ts}.html")

    q_table = _load_json(QTABLE_PATH, {})
    stats   = _load_json(STATS_PATH,  {})

    ql_section = _build_qlearning_section(q_table, stats)

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bot3 Q-Learning - Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body          {{ background: #0d1117; color: #e6edf3; }}
    .card         {{ background: #161b22; border: 1px solid #30363d; }}
    .card-header  {{ background: #21262d; border-bottom: 1px solid #30363d; }}
    .stat-box     {{ display:flex; flex-direction:column; padding:12px; background:#0d1117; border-radius:6px; }}
    .stat-label   {{ font-size:.75rem; color:#8b949e; }}
    .stat-value   {{ font-size:1.4rem; font-weight:700; color:#58a6ff; }}
    h6            {{ color:#8b949e; }}
  </style>
</head>
<body>
<div class="container-fluid py-4">
  <h3 class="mb-1">Bot3 Q-Learning</h3>
  <p class="text-muted mb-4">Generated: {generated_at}</p>

  {ql_section}

</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Dashboard generated: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    path = generate()
    print(f"Dashboard: {path}")
