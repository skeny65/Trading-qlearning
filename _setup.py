"""script temporal de setup — crea directorios necesarios para el proyecto.

EJECUTAR UNA SOLA VEZ desde la raiz del repositorio:
    python _setup.py
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))

dirs = [
    "core", "manager", "strategies/pinescript", "data/qlearning",
    "data/trades/archive", "data/reports", "dashboard/output", "dashboard/history",
    "utils", "scripts", "docs", "tests/fixtures", "logs/dry_run", "signals"
]

for d in dirs:
    path = os.path.join(BASE, d)
    os.makedirs(path, exist_ok=True)
    print(f"  + {d}")

# __init__.py files
for pkg in ["core", "manager", "strategies", "utils", "tests"]:
    p = os.path.join(BASE, pkg, "__init__.py")
    if not os.path.exists(p):
        open(p, "w").close()
        print(f"  + {pkg}/__init__.py")

# .gitkeep files
for d in ["data/qlearning", "data/trades", "data/reports",
          "dashboard/output", "dashboard/history", "logs/dry_run", "signals"]:
    p = os.path.join(BASE, d, ".gitkeep")
    if not os.path.exists(p):
        open(p, "w").close()

print("\n✅ directorios creados. ahora ejecuta: python setup_project.py")
