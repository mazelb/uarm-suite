"""Draw-shapes: a simple runnable activity proving the framework is generic.

Draws a square, triangle, star, or circle of a given ``size`` (half-extent /
outer radius, mm) centered at ``(center_x, center_y)``. Like tic-tac-toe it
commands tool-tip Cartesian positions as the pen contact point and lifts the
pen between strokes; see :mod:`activities._draw`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from drawing import load_drawing_config

from . import register_activity
from ._draw import Stroke, draw_strokes

if TYPE_CHECKING:
    from arm import UArm

SHAPES = ("square", "triangle", "star", "circle")


def _polygon(
    cx: float, cy: float, radius: float, vertices: int, phase: float = math.pi / 2
) -> Stroke:
    """A closed regular polygon (first point repeated at the end)."""
    pts: Stroke = []
    for i in range(vertices):
        t = phase + 2.0 * math.pi * i / vertices
        pts.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
    pts.append(pts[0])
    return pts


def shape_strokes(shape: str, size: float, center_x: float, center_y: float) -> list[Stroke]:
    """Return the stroke list (each a closed polyline) for ``shape``."""
    cx, cy = center_x, center_y
    if shape == "square":
        s = size
        return [
            [
                (cx - s, cy - s),
                (cx - s, cy + s),
                (cx + s, cy + s),
                (cx + s, cy - s),
                (cx - s, cy - s),
            ]
        ]
    if shape == "triangle":
        return [_polygon(cx, cy, size, 3)]
    if shape == "circle":
        return [_polygon(cx, cy, size, 24)]
    if shape == "star":
        inner = size * 0.4
        pts: Stroke = []
        for i in range(10):  # 5 outer + 5 inner alternating
            r = size if i % 2 == 0 else inner
            t = math.pi / 2 + i * math.pi / 5
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        pts.append(pts[0])
        return [pts]
    raise ValueError(f"unknown shape {shape!r}; choose one of {', '.join(SHAPES)}")


@register_activity
class DrawShapes:
    """Runnable activity: draw a chosen shape at a position."""

    slug = "draw-shapes"
    name = "Draw Shapes"
    description = "Draw a square, triangle, star, or circle at a position."

    def __init__(self) -> None:
        d = load_drawing_config()
        self.shape = "square"
        self.size = 40.0
        self.center_x = 250.0
        self.center_y = 0.0
        self.table_z = d.table_z  # persisted pen-down height (drawing.json)
        self.pen_up = d.pen_up
        self.wrist = d.wrist
        self.feed = d.feed  # mm/s feeds; None = suite defaults
        self.travel_feed = d.travel_feed

    def configure(self, options: dict) -> None:
        for key in (
            "shape",
            "size",
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
        strokes = shape_strokes(self.shape, self.size, self.center_x, self.center_y)
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
