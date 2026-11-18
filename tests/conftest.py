"""pytest configuration for confhub tests."""
import sys
from pathlib import Path

# Ensure the src directory is on sys.path so confhub is importable without installation.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
