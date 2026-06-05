"""Pytest conftest — adds the project root to sys.path so flat-layout modules
(config.py, kinematics.py, ...) are importable from tests/."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _isolate_drawing_config(tmp_path, monkeypatch):
    """Point drawing.json at a throwaway path for every test.

    A real calibrated drawing.json on the dev/Pi machine must never change test
    outcomes — the sim suite has to stay green with no hardware (Phase 8). With
    no file present, load_drawing_config() returns the historical defaults
    (table_z=0, pen_up=20).
    """
    import drawing

    monkeypatch.setattr(drawing, "DRAWING_PATH", tmp_path / "drawing.json")
