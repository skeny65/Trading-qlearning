#!/usr/bin/env python3
"""Inline setup runner."""
import os
import subprocess
import sys

# Change to the project directory
os.chdir(r"c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning")

# Execute _setup.py
result = subprocess.run([sys.executable, "_setup.py"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
sys.exit(result.returncode)
