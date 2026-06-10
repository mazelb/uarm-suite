"""Geometry, joint limits, and servo wiring constants for the uArm Swift.

Numeric constants only — no I/O, no behavior. Tune these after measuring
the physical arm.
"""

from __future__ import annotations

from typing import TypedDict

# ---------------------------------------------------------------------------
# Geometry (millimeters). Origin = base axis at the table surface.
# ---------------------------------------------------------------------------

H_BASE: float = 80.0  # table -> J1 (shoulder) axis
L1: float = 142.0  # J1 axis -> elbow joint
L2: float = 158.0  # elbow joint -> wrist axis
L_TOOL: float = 56.0  # wrist axis -> tool tip (horizontal offset in arm plane)

# Approximate reachable Cartesian envelope. Real shape is a torus segment;
# these are loose bounding-box hints for the CLI / UI.
X_RANGE: tuple[float, float] = (140.0, 320.0)
Y_RANGE: tuple[float, float] = (-200.0, 200.0)
Z_RANGE: tuple[float, float] = (-50.0, 150.0)

# ---------------------------------------------------------------------------
# Joint limits (degrees). 0° conventions:
#   J0 = 0  -> arm points along +X (straight forward from base)
#   J1 = 0  -> upper arm horizontal, extended forward
#   J2 = 0  -> forearm horizontal (absolute angle, parallel-linkage frame)
#             positive = forearm tilts up; negative = forearm tilts down
#   J3 = 0  -> wrist neutral
# ---------------------------------------------------------------------------

J0_LIMITS: tuple[float, float] = (-90.0, 90.0)
J1_LIMITS: tuple[float, float] = (0.0, 135.0)
J2_LIMITS: tuple[float, float] = (-135.0, 90.0)
J3_LIMITS: tuple[float, float] = (-90.0, 90.0)

# Coupled parallelogram constraint. The two driven linkages cannot fold past
# each other. In the legacy "elbow bend" convention this was `j1 + j2 < 180°`;
# under the forearm-absolute convention it becomes a coupled floor on j2:
#     j2 > 2*j1 - 180   (degrees)
# parallelogram_floor_deg(j1) returns the strict lower bound j2 must clear.


def parallelogram_floor_deg(j1_deg: float) -> float:
    """Strict lower bound for j2 given j1 (parallelogram linkage constraint)."""
    return 2.0 * j1_deg - 180.0


# ---------------------------------------------------------------------------
# PCA9685 wiring.
# ---------------------------------------------------------------------------

I2C_ADDRESS: int = 0x40
PWM_FREQUENCY_HZ: int = 50

CHANNELS: dict[str, int] = {
    "J0": 0,  # base rotation (yaw)
    "J1": 1,  # shoulder / front linkage
    "J2": 2,  # elbow / rear linkage
    "J3": 3,  # wrist rotation
    "PUMP": 4,  # reserved, stub
    "GRIPPER": 5,  # reserved, stub
}


class ServoCalibration(TypedDict):
    """Per-channel servo trim.

    `zero_deg` is the servo-frame angle that maps to joint-frame 0°.
    `direction` is +1 if increasing joint angle = increasing servo angle,
    -1 if reversed (servo mounted backwards relative to joint convention).
    `min_us` / `max_us` are the PWM pulse widths for servo angles 0 and 180.
    """

    min_us: int
    max_us: int
    zero_deg: float
    direction: int  # +1 or -1


# Identity calibration. Tune per-servo against the physical arm.
SERVO_CALIBRATION: dict[int, ServoCalibration] = {
    0: {"min_us": 500, "max_us": 2500, "zero_deg": 90.0, "direction": +1},
    1: {"min_us": 500, "max_us": 2500, "zero_deg": 90.0, "direction": +1},
    2: {"min_us": 500, "max_us": 2500, "zero_deg": 90.0, "direction": +1},
    3: {"min_us": 500, "max_us": 2500, "zero_deg": 90.0, "direction": +1},
}

# ---------------------------------------------------------------------------
# Motion defaults.
# ---------------------------------------------------------------------------

SLOW_HOME_DEG_PER_SEC: float = 30.0
DEFAULT_DEG_PER_SEC: float = 180.0
SIM_UPDATE_HZ: float = 50.0

# Drawing feed rates (Phase 8B). Cartesian tool-tip speeds in mm/s — distinct
# from the joint speeds above. Strokes are subdivided into DRAW_STEP_MM
# straight-line steps so the pen tip follows the stroke geometry instead of
# the curve a joint-space slew would trace. Tune on paper.
DRAW_FEED_MM_S: float = 40.0  # pen on paper
TRAVEL_FEED_MM_S: float = 120.0  # pen-up travel between strokes
DRAW_STEP_MM: float = 2.0  # linear-interpolation step length
