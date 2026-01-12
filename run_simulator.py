#!/usr/bin/env python3
"""Runner script to start the simulator."""
import os
import sys
import subprocess

# Set working directory
script_dir = os.path.dirname(os.path.abspath(__file__))
simulator_dir = os.path.join(script_dir, "simulator")
os.chdir(simulator_dir)

# Add simulator to path
sys.path.insert(0, simulator_dir)

# Set environment
os.environ["BACKEND_URL"] = "http://localhost:8000"

# Run simulator
subprocess.run([
    sys.executable, "simulate.py",
    "--speed", "5",
    "--minutes", "3"
])
