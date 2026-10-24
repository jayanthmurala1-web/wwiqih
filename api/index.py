import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.app import app  # noqa: E402,F401
