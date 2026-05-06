import os
import sys

# Change to project directory
os.chdir(r'c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning')

# Create all directories
dirs = [
    "core", "manager", "strategies/pinescript", "data/qlearning",
    "data/trades/archive", "data/reports", "dashboard/output", "dashboard/history",
    "utils", "scripts", "docs", "tests/fixtures", "logs/dry_run", "signals"
]

print("Creating directories...")
for d in dirs:
    try:
        os.makedirs(d, exist_ok=True)
        print(f"  created: {d}")
    except Exception as e:
        print(f"  error creating {d}: {e}")

# Create __init__.py files
print("\nCreating __init__.py files...")
for pkg in ["core", "manager", "strategies", "utils", "tests"]:
    p = os.path.join(pkg, "__init__.py")
    try:
        if not os.path.exists(p):
            open(p, "w").close()
            print(f"  created: {pkg}/__init__.py")
        else:
            print(f"  exists: {pkg}/__init__.py")
    except Exception as e:
        print(f"  error creating {p}: {e}")

# Create .gitkeep files
print("\nCreating .gitkeep files...")
for d in ["data/qlearning", "data/trades", "data/reports",
          "dashboard/output", "dashboard/history", "logs/dry_run", "signals"]:
    p = os.path.join(d, ".gitkeep")
    try:
        if not os.path.exists(p):
            open(p, "w").close()
            print(f"  created: {d}/.gitkeep")
        else:
            print(f"  exists: {d}/.gitkeep")
    except Exception as e:
        print(f"  error creating {p}: {e}")

print("\nSetup complete!")
