"""Draw-text: write a short message with the pen.

A built-in single-stroke vector font (no fills — every glyph is a few
polylines, exactly like the tic-tac-toe marks) covering A-Z, 0-9, space and
basic punctuation. Glyphs live on a 4x6-unit cell; ``size`` is the capital
height in mm.

Page orientation matches the tic-tac-toe board: "up" on the page is +X (away
from the base) and the text advances toward -Y, so it reads left-to-right for
the operator looking out along +X. Like the other drawing activities it goes
through :func:`activities._draw.draw_strokes`, inheriting straight-line
motion, feed pacing, and whole-path validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from drawing import load_drawing_config

from . import register_activity
from ._draw import Stroke, draw_strokes

if TYPE_CHECKING:
    from arm import UArm

# Glyph cell in font units: x 0..4 (left -> right), y 0..6 (baseline -> cap).
GLYPH_W = 4.0
GLYPH_H = 6.0

# Each glyph: list of strokes, each stroke a polyline of (x, y) font units.
_GLYPHS: dict[str, list[Stroke]] = {
    "A": [[(0, 0), (2, 6), (4, 0)], [(1, 3), (3, 3)]],
    "B": [
        [(0, 0), (0, 6)],
        [(0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)],
        [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)],
    ],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2, 6), (4, 4), (4, 2), (2, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 3), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [[(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]],
    "P": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]],
    "Q": [
        [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)],
        [(2.5, 1.5), (4, 0)],
    ],
    "R": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(2, 3), (4, 0)]],
    "S": [
        [
            (4, 5),
            (3, 6),
            (1, 6),
            (0, 5),
            (0, 4),
            (1, 3),
            (3, 3),
            (4, 2),
            (4, 1),
            (3, 0),
            (1, 0),
            (0, 1),
        ]
    ],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 4), (3, 0), (4, 6)]],
    "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "0": [
        [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)],
        [(1, 1), (3, 5)],
    ],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [
        [(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3)],
        [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)],
    ],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3.5), (3, 3.5), (4, 2.5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "6": [[(3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "7": [[(0, 6), (4, 6), (1.5, 0)]],
    "8": [
        [
            (1, 3),
            (0, 4),
            (0, 5),
            (1, 6),
            (3, 6),
            (4, 5),
            (4, 4),
            (3, 3),
            (1, 3),
            (0, 2),
            (0, 1),
            (1, 0),
            (3, 0),
            (4, 1),
            (4, 2),
            (3, 3),
        ]
    ],
    "9": [[(4, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]],
    " ": [],
    "-": [[(1, 3), (3, 3)]],
    "+": [[(2, 1), (2, 5)], [(0, 3), (4, 3)]],
    ".": [[(2, 0), (2, 0.3)]],
    ",": [[(2, 0.5), (1.5, -0.5)]],
    "!": [[(2, 6), (2, 2)], [(2, 0), (2, 0.3)]],
    "?": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (2, 2.5), (2, 1.8)], [(2, 0), (2, 0.3)]],
    ":": [[(2, 4), (2, 4.3)], [(2, 1), (2, 1.3)]],
    "'": [[(2, 6), (2, 5)]],
}

SUPPORTED = "".join(sorted(_GLYPHS))


def text_strokes(
    text: str,
    size: float,
    center_x: float,
    center_y: float,
    spacing: float = 2.0,
) -> list[Stroke]:
    """Stroke list (world mm) writing ``text`` centered on (center_x, center_y).

    ``size`` is the capital height in mm; ``spacing`` is the gap between
    glyph cells in font units (monospace advance = GLYPH_W + spacing).
    Lowercase input is uppercased. Raises ValueError for unsupported
    characters or a non-positive size.
    """
    if size <= 0:
        raise ValueError(f"size must be positive mm, got {size}")
    text = text.upper()
    bad = sorted({ch for ch in text if ch not in _GLYPHS})
    if bad:
        listed = ", ".join(repr(ch) for ch in bad)
        raise ValueError(f"unsupported character(s) {listed}; supported: {SUPPORTED!r}")
    if not text:
        return []

    u = size / GLYPH_H  # mm per font unit
    advance = GLYPH_W + spacing
    total_w = (len(text) * advance - spacing) * u  # no trailing gap

    strokes: list[Stroke] = []
    for i, ch in enumerate(text):
        left = i * advance * u  # glyph cell's left edge, mm from the string start
        for stroke in _GLYPHS[ch]:
            strokes.append(
                [
                    (
                        # Page "up" is +X; advancing right is -Y.
                        center_x + (gy - GLYPH_H / 2) * u,
                        center_y + total_w / 2 - left - gx * u,
                    )
                    for gx, gy in stroke
                ]
            )
    return strokes


@register_activity
class DrawText:
    """Runnable activity: write a short message at a position."""

    slug = "draw-text"
    name = "Draw Text"
    description = "Write a short message (A-Z, 0-9, basic punctuation) with the pen."

    def __init__(self) -> None:
        d = load_drawing_config()
        self.text = "HI!"
        self.size = 30.0  # capital height, mm
        self.spacing = 2.0  # inter-glyph gap, font units
        self.center_x = 250.0
        self.center_y = 0.0
        self.table_z = d.table_z  # persisted pen-down height (drawing.json)
        self.pen_up = d.pen_up
        self.wrist = d.wrist
        self.feed = d.feed  # mm/s feeds; None = suite defaults
        self.travel_feed = d.travel_feed

    def configure(self, options: dict) -> None:
        for key in (
            "text",
            "size",
            "spacing",
            "center_x",
            "center_y",
            "table_z",
            "pen_up",
            "wrist",
            "feed",
            "travel_feed",
        ):
            if key in options:
                setattr(self, key, options[key])

    def setup(self, arm: UArm) -> None:
        arm.home(blocking=True)

    def run(self, arm: UArm) -> None:
        strokes = text_strokes(
            str(self.text), self.size, self.center_x, self.center_y, spacing=self.spacing
        )
        draw_strokes(
            arm,
            strokes,
            table_z=self.table_z,
            pen_up_z=self.table_z + self.pen_up,
            wrist=self.wrist,
            feed=self.feed,
            travel_feed=self.travel_feed,
        )

    def cleanup(self, arm: UArm) -> None:
        return None
