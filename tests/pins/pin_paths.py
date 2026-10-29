"""Folders the pins read from and write to."""

from pathlib import Path

PINS_DIR = Path(__file__).resolve().parent
REPO_ROOT = PINS_DIR.parents[1]
