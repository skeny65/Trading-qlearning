#!/usr/bin/env python3
"""Setup script to create directories and files."""
import os
import sys

BASE = r"c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning"

dirs = [
    "core", "manager", "strategies/pinescript", "data/qlearning",
    "data/trades/archive", "data/reports", "dashboard/output", "dashboard/history",
    "utils", "scripts", "docs", "tests/fixtures", "logs/dry_run", "signals"
]

print("Creating directories...")
for d in dirs:
    path = os.path.join(BASE, d)
    os.makedirs(path, exist_ok=True)
    print(f"  created: {d}")

# __init__.py files
print("\nCreating __init__.py files...")
for pkg in ["core", "manager", "strategies", "utils", "tests"]:
    p = os.path.join(BASE, pkg, "__init__.py")
    if not os.path.exists(p):
        open(p, "w").close()
        print(f"  created: {pkg}/__init__.py")

# .gitkeep files
print("\nCreating .gitkeep files...")
for d in ["data/qlearning", "data/trades", "data/reports",
          "dashboard/output", "dashboard/history", "logs/dry_run", "signals"]:
    p = os.path.join(BASE, d, ".gitkeep")
    if not os.path.exists(p):
        open(p, "w").close()
        print(f"  created: {d}/.gitkeep")

print("\nSetup complete!")
