"""Entry point for running the application with 'uvicorn main:app' from project root.

This module adds the src directory to sys.path and imports the app from src.main.
"""

import sys
from pathlib import Path

# Add src directory to path so that 'from src.xxx import yyy' works
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.main import app

__all__ = ["app"]
