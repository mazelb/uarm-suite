"""Pen-drawing helpers shared by drawing activities.

A *stroke* is a polyline: a list of ``(x, y)`` points in mm, drawn at the
table contact height with the pen down. Between strokes the pen lifts to
``pen_up_z``. See the module note in :mod:`activities.tic_tac_toe` for why the
commanded tool-tip position is treated as the pen contact point (the arm has no
wrist pitch; the physical pen offset is absorbed into Z calibration).

Every point is validated against the workspace *before* any motion, so a path
never half-draws and then faults mid-stroke.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    speed: float | None = None,
) -> None:
    """Draw each stroke with pen-up moves between them.

    Validates the whole path first. For each stroke: move above the first point
    at ``pen_up_z``, lower to ``table_z``, traverse the polyline, then lift.
    """
    validate_reachable(strokes, table_z=table_z, pen_up_z=pen_up_z, wrist=wrist)

    def goto(x: float, y: float, z: float) -> None:
        arm.set_position(x, y, z, wrist=wrist, speed=speed, blocking=True)

    for stroke in strokes:
        if not stroke:
            continue
        x0, y0 = stroke[0]
        goto(x0, y0, pen_up_z)  # approach above the start
        goto(x0, y0, table_z)  # pen down
        for x, y in stroke[1:]:
            goto(x, y, table_z)  # draw
        xl, yl = stroke[-1]
        goto(xl, yl, pen_up_z)  # pen up
