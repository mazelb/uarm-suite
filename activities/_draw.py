"""Pen-drawing helpers shared by drawing activities.

A *stroke* is a polyline: a list of ``(x, y)`` points in mm, drawn at the
table contact height with the pen down. Between strokes the pen lifts to
``pen_up_z``. See the module note in :mod:`activities.tic_tac_toe` for why the
commanded tool-tip position is treated as the pen contact point (the arm has no
wrist pitch; the physical pen offset is absorbed into Z calibration).

Every point is validated against the workspace *before* any motion, so a path
never half-draws and then faults mid-stroke.

Motion is straight-line via :meth:`UArm.move_linear`: pen-down segments run at
``feed`` mm/s and pen-up travel at ``travel_feed`` (defaults from config /
``drawing.json``). Feed is a Cartesian tool-tip speed — line quality on paper
depends on it, which is why it is tuned separately from joint speeds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import DRAW_FEED_MM_S, TRAVEL_FEED_MM_S
from kinematics import WorkspaceError, in_workspace

if TYPE_CHECKING:
    from arm import UArm

Point = tuple[float, float]
Stroke = list[Point]


def validate_reachable(
    strokes: list[Stroke],
    *,
    table_z: float,
    pen_up_z: float,
    wrist: float = 0.0,
) -> None:
    """Raise :class:`WorkspaceError` if any stroke point is unreachable.

    Checks both the pen-down (``table_z``) and pen-up (``pen_up_z``) heights,
    since the path visits both.
    """
    for stroke in strokes:
        for x, y in stroke:
            for z in (table_z, pen_up_z):
                if not in_workspace(x, y, z, wrist=wrist):
                    raise WorkspaceError(
                        f"drawing point ({x:.1f}, {y:.1f}, {z:.1f}) is outside the workspace"
                    )


def draw_strokes(
    arm: UArm,
    strokes: list[Stroke],
    *,
    table_z: float,
    pen_up_z: float,
    wrist: float = 0.0,
    feed: float | None = None,
    travel_feed: float | None = None,
) -> None:
    """Draw each stroke with pen-up moves between them.

    Validates the whole path first. For each stroke: move above the first point
    at ``pen_up_z``, lower to ``table_z``, traverse the polyline, then lift.
    Lowering the pen uses the (slower) draw ``feed`` so the tip lands gently.
    ``None`` feeds fall back to the suite defaults.
    """
    validate_reachable(strokes, table_z=table_z, pen_up_z=pen_up_z, wrist=wrist)
    feed = feed if feed is not None else DRAW_FEED_MM_S
    travel_feed = travel_feed if travel_feed is not None else TRAVEL_FEED_MM_S

    for stroke in strokes:
        if not stroke:
            continue
        x0, y0 = stroke[0]
        arm.move_linear(x0, y0, pen_up_z, wrist=wrist, feed=travel_feed)  # approach
        arm.move_linear(x0, y0, table_z, wrist=wrist, feed=feed)  # pen down, gently
        for x, y in stroke[1:]:
            arm.move_linear(x, y, table_z, wrist=wrist, feed=feed)  # draw
        xl, yl = stroke[-1]
        arm.move_linear(xl, yl, pen_up_z, wrist=wrist, feed=travel_feed)  # pen up
