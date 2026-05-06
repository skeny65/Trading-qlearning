#!/usr/bin/env python3
import os

os.chdir(r'c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning')

# Create directories
for dir_path in [
    "core", "manager", "strategies", "strategies/pinescript", "data", "data/qlearning",
    "data/trades", "data/trades/archive", "data/reports", "dashboard", "dashboard/output", 
    "dashboard/history", "utils", "scripts", "docs", "tests", "tests/fixtures", 
    "logs", "logs/dry_run", "signals"
]:
    try:
        os.makedirs(dir_path, exist_ok=True)
    except:
        pass

# Create __init__.py files
for f in ["core/__init__.py", "manager/__init__.py", "strategies/__init__.py", "utils/__init__.py", "tests/__init__.py"]:
    try:
        open(f, 'w').close()
    except:
        pass

# Create .gitkeep files
for f in ["data/qlearning/.gitkeep", "data/trades/.gitkeep", "data/reports/.gitkeep", 
          "dashboard/output/.gitkeep", "dashboard/history/.gitkeep", "logs/dry_run/.gitkeep", "signals/.gitkeep"]:
    try:
        open(f, 'w').close()
    except:
        pass

print("Setup completed!")
