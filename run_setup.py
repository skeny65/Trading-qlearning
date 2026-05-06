#!/usr/bin/env python3
"""Execute the setup directly."""
import os
import sys

# Add the current directory to path
sys.path.insert(0, os.getcwd())

# Execute _setup.py
exec(open('_setup.py').read())
