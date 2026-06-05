"""Pen / drawing calibration — the table-contact Z and travel clearance.

The arm has no wrist pitch, so the commanded tool-tip Z *is* the pen contact
height. ``table_z`` is that height for the currently mounted pen — the one
physical unknown every drawing path depends on. It is found once (see
``uarm pen calibrate``) and persisted here in ``drawing.json``, kept separate
from servo trim (``calibration.json``) because it is a Cartesian / pen concern,
not servo-frame trim.

Pure config + geometry; no hardware imports, no I/O beyond the JSON file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kinematics import in_workspace

DRAWING_PATH = Path("drawing.json")

Point = tuple[float, float]


@dataclass
class DrawingConfig:
    """Persisted pen geometry. Defaults match the historical hardcoded values
    (``table_z=0``, ``pen_up=20``) so an absent ``drawing.json`` behaves exactly
    like pre-Phase-8 sim."""

    table_z: float = 0.0  # pen-down contact height (the calibrated unknown)
    pen_up: float = 20.0  # travel clearance above table_z between strokes
    wrist: float = 0.0  # wrist angle held while drawing
    pen_label: str = ""  # which pen this was calibrated for (free text)

    @property
    def pen_up_z(self) -> float:
        return self.table_z + self.pen_up


def load_drawing_config(path: Path | None = None) -> DrawingConfig:
    """Load ``drawing.json``, or return defaults if it does not exist.

    Unknown keys are ignored so an old file with extra fields still loads.
    ``path`` is resolved at call time (not bound as a default) so tests can
    redirect ``DRAWING_PATH`` via monkeypatch.
    """
    path = path or DRAWING_PATH
    if not path.exists():
        return DrawingConfig()
    data = json.loads(path.read_text())
    known = set(DrawingConfig.__dataclass_fields__)
    return DrawingConfig(**{k: v for k, v in data.items() if k in known})


def save_drawing_config(cfg: DrawingConfig, path: Path | None = None) -> Path:
    """Persist ``cfg`` to ``drawing.json`` (pretty-printed). Returns the path."""
    path = path or DRAWING_PATH
    path.write_text(json.dumps(asdict(cfg), indent=2))
    return path


# ---------------------------------------------------------------------------
# Grid placement helpers (dry-run / jog-to-corner)
# ---------------------------------------------------------------------------


def grid_corners(center_x: float, center_y: float, cell: float) -> list[Point]:
    """The four outer corners of the 3x3 tic-tac-toe grid (mm).

    The grid's outer half-extent is ``1.5 * cell`` (matches
    ``tic_tac_toe.grid_strokes``). Ordered as a rectangle loop so a jog visits
    them in sequence rather than crossing the paper diagonally.
    """
    half = 1.5 * cell
    return [
        (center_x - half, center_y - half),
        (center_x - half, center_y + half),
        (center_x + half, center_y + half),
        (center_x + half, center_y - half),
    ]


def unreachable_corners(corners: list[Point], z: float, *, wrist: float = 0.0) -> list[Point]:
    """Return the subset of ``corners`` that are outside the workspace at ``z``.

    An empty list means the whole grid footprint is reachable at that height.
    """
    return [(x, y) for (x, y) in corners if not in_workspace(x, y, z, wrist=wrist)]
