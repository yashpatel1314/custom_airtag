"""Test setup. Tests import the server modules directly, so the server
directory has to be importable regardless of where pytest is invoked from."""

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))
