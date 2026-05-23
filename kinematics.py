"""Pure-function forward and inverse kinematics for the uArm Swift.

The arm is a parallel-linkage 4-DOF arm. After reducing by base rotation and
the horizontal tool offset, IK becomes a standard 2-link planar problem in the
(r, z) plane.

Public API uses degrees and millimeters. Origin is the base axis at the table
surface, so the J1 axis is at z = H_BASE.

Logical joint angle convention (these are the IK outputs, NOT servo angles —
see config.SERVO_CALIBRATION for the servo-frame mapping):

    j0  base rotation about vertical (atan2(y, x))
    j1  upper-arm absolute angle from horizontal in the arm plane
        (0 = upper arm horizontal, 90 = upper arm pointing straight up)
    j2  forearm absolute angle from horizontal in the arm plane
        (0 = forearm horizontal, positive = wrist above elbow,
         negative = wrist below elbow). NOT the elbow bend angle.
    j3  wrist rotation about vertical (independent; does not affect tip XYZ
        under the assumption that the tool points radially outward)

Why j2 is "absolute" rather than "elbow bend": the uArm Swift is a parallel
linkage. Both servos drive absolute-angle linkages whose physical limits are
most naturally expressed in their own frames. The coupled limit (linkages
can't fold through each other) becomes `j2 > 2*j1 - 180°`.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from config import (
    H_BASE,
    J0_LIMITS,
    J1_LIMITS,
    J2_LIMITS,
    J3_LIMITS,
    L1,
    L2,
    L_TOOL,
    parallelogram_floor_deg,
)

# Numerical slack for floating-point comparisons at workspace boundaries (mm).
_REACH_TOL_MM: float = 1e-6


class WorkspaceError(ValueError):
    """Target is outside the geometric reach of the arm."""


class JointLimitError(ValueError):
    """A required joint angle violates a configured limit."""


class JointAngles(NamedTuple):
    j0: float
    j1: float
    j2: float
    j3: float


class Position(NamedTuple):
    x: float
    y: float
    z: float


# ---------------------------------------------------------------------------
# Forward kinematics
# ---------------------------------------------------------------------------


def forward_kinematics(j0: float, j1: float, j2: float, j3: float = 0.0) -> Position:
    """Compute tool-tip position from joint angles."""
    del j3  # unused; tool assumed to point radially outward

    t0 = math.radians(j0)
    t1 = math.radians(j1)
    t2 = math.radians(j2)

    # 2-link planar geometry in the arm's (r, z) plane. Both segments use
    # absolute angles from horizontal (parallel-linkage convention).
    elbow_r = L1 * math.cos(t1)
    elbow_z = L1 * math.sin(t1)
    wrist_r = elbow_r + L2 * math.cos(t2)
    wrist_z = elbow_z + L2 * math.sin(t2)

    tip_r = wrist_r + L_TOOL
    tip_z = wrist_z + H_BASE

    return Position(
        x=tip_r * math.cos(t0),
        y=tip_r * math.sin(t0),
        z=tip_z,
    )


# ---------------------------------------------------------------------------
# Inverse kinematics (elbow-up branch only)
# ---------------------------------------------------------------------------


def inverse_kinematics(x: float, y: float, z: float, wrist: float = 0.0) -> JointAngles:
    """Compute joint angles placing the tool tip at (x, y, z) in mm.

    Picks the elbow-up branch. Raises WorkspaceError if outside reach,
    JointLimitError if any joint or coupled limit is violated.
    """
    t0 = math.atan2(y, x)
    r = math.hypot(x, y) - L_TOOL
    zp = z - H_BASE

    d_sq = r * r + zp * zp
    d = math.sqrt(d_sq)

    reach_max = L1 + L2
    reach_min = abs(L1 - L2)
    if d > reach_max + _REACH_TOL_MM:
        raise WorkspaceError(
            f"target ({x:.1f}, {y:.1f}, {z:.1f}) is {d:.1f} mm from shoulder; "
            f"max reach {reach_max:.1f} mm"
        )
    if d < reach_min - _REACH_TOL_MM:
        raise WorkspaceError(
            f"target ({x:.1f}, {y:.1f}, {z:.1f}) is {d:.1f} mm from shoulder; "
            f"min reach {reach_min:.1f} mm (dead zone around base)"
        )

    # Law of cosines. Clamp absorbs sub-ulp drift at the reach extremes; values
    # physically out of [-1, 1] would already have failed the reach checks above.
    cos_alpha = (L1 * L1 + L2 * L2 - d_sq) / (2.0 * L1 * L2)
    cos_beta = (L1 * L1 + d_sq - L2 * L2) / (2.0 * L1 * d)
    alpha = math.acos(_clamp_unit(cos_alpha))
    beta = math.acos(_clamp_unit(cos_beta))

    # Elbow-up branch. j1 is upper-arm absolute angle from horizontal;
    # j2 is forearm absolute angle from horizontal (parallelogram convention).
    t1 = math.atan2(zp, r) + beta
    t2 = t1 + alpha - math.pi

    # TODO: when j1 > pi/2 the wrist crosses into -X relative to the arm plane;
    # the round-trip then recovers a mirror solution via j0 = ±180°. Such
    # targets are outside the j0 limit anyway, so we don't try to flip the
    # base here. Revisit if reaching behind the base ever matters.

    angles = JointAngles(
        j0=math.degrees(t0),
        j1=math.degrees(t1),
        j2=math.degrees(t2),
        j3=wrist,
    )
    _check_joint_limits(angles)
    return angles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def in_workspace(x: float, y: float, z: float, wrist: float = 0.0) -> bool:
    """Return True if (x, y, z) is reachable under both geometry and joint limits."""
    try:
        inverse_kinematics(x, y, z, wrist=wrist)
    except (WorkspaceError, JointLimitError):
        return False
    return True


def _clamp_unit(v: float) -> float:
    if v > 1.0:
        return 1.0
    if v < -1.0:
        return -1.0
    return v


def _check_joint_limits(angles: JointAngles) -> None:
    for name, value, (lo, hi) in (
        ("j0", angles.j0, J0_LIMITS),
        ("j1", angles.j1, J1_LIMITS),
        ("j2", angles.j2, J2_LIMITS),
        ("j3", angles.j3, J3_LIMITS),
    ):
        if not (lo <= value <= hi):
            raise JointLimitError(f"{name} = {value:.2f}° out of range [{lo:.1f}, {hi:.1f}]")
    # Parallelogram coupling: the two driven linkages cannot fold through each
    # other. In the old "elbow bend" convention this was `j1 + j2 < 180°`.
    # Translated to the forearm-absolute convention: `j2 > 2·j1 − 180°`.
    floor = parallelogram_floor_deg(angles.j1)
    if angles.j2 <= floor:
        raise JointLimitError(
            f"j2 = {angles.j2:.2f}° must be > {floor:.2f}° "
            f"(parallelogram linkage constraint: j2 > 2·j1 − 180°, with j1 = {angles.j1:.2f}°)"
        )
