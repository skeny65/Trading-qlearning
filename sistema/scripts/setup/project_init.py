#!/usr/bin/env python3
"""Auto-execute setup on import."""
import os

# Change to script directory
_current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_current_dir)

# Create directories
_dirs = [
    "core", "manager", "strategies/pinescript", "data/qlearning",
    "data/trades/archive", "data/reports", "dashboard/output", "dashboard/history",
    "utils", "scripts", "docs", "tests/fixtures", "logs/dry_run", "signals"
]

for _d in _dirs:
    os.makedirs(_d, exist_ok=True)

# Create __init__.py files
for _pkg in ["core", "manager", "strategies", "utils", "tests"]:
    _p = os.path.join(_pkg, "__init__.py")
    if not os.path.exists(_p):
        open(_p, "w").close()

# Create .gitkeep files
for _d in ["data/qlearning", "data/trades", "data/reports",
           "dashboard/output", "dashboard/history", "logs/dry_run", "signals"]:
    _p = os.path.join(_d, ".gitkeep")
    if not os.path.exists(_p):
        open(_p, "w").close()
