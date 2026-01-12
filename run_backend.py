#!/usr/bin/env python3
"""Runner script to start the backend server."""
import os
import sys

# Set working directory
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(script_dir, "backend")
os.chdir(backend_dir)

# Add backend to path
sys.path.insert(0, backend_dir)

# Create data directory
os.makedirs("data", exist_ok=True)

if __name__ == "__main__":
    # Run uvicorn
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
