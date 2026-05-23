"""Pytest conftest — adds the project root to sys.path so flat-layout modules
(config.py, kinematics.py, ...) are importable from tests/."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
