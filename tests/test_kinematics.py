"""Tests for kinematics.py — FK/IK correctness, round-trip, boundaries, limits."""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

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
from kinematics import (
    JointAngles,
    JointLimitError,
    Position,
    WorkspaceError,
    forward_kinematics,
    in_workspace,
    inverse_kinematics,
)

# ---------------------------------------------------------------------------
# FK sanity checks against hand-derived configurations
# ---------------------------------------------------------------------------


def test_fk_fully_extended_horizontal():
    """j1=0, j2=0 -> both segments horizontal forward; tip at (L1+L2+L_TOOL, 0, H_BASE)."""
    p = forward_kinematics(j0=0, j1=0, j2=0)
    assert p.x == pytest.approx(L1 + L2 + L_TOOL, abs=1e-9)
    assert p.y == pytest.approx(0.0, abs=1e-9)
    assert p.z == pytest.approx(H_BASE, abs=1e-9)


def test_fk_straight_up():
    """j1=90, j2=90 -> both segments vertical; tip offset by L_TOOL horizontally."""
    p = forward_kinematics(j0=0, j1=90, j2=90)
    assert p.x == pytest.approx(L_TOOL, abs=1e-9)
    assert p.y == pytest.approx(0.0, abs=1e-9)
    assert p.z == pytest.approx(H_BASE + L1 + L2, abs=1e-9)


def test_fk_upper_arm_up_forearm_horizontal():
    """j1=90 (upper arm vertical), j2=0 (forearm horizontal) -> L-shape."""
    p = forward_kinematics(j0=0, j1=90, j2=0)
    assert p.x == pytest.approx(L2 + L_TOOL, abs=1e-9)
    assert p.y == pytest.approx(0.0, abs=1e-9)
    assert p.z == pytest.approx(H_BASE + L1, abs=1e-9)


def test_fk_base_rotation_90():
    """j0=90 swings the whole arm to +Y."""
    p = forward_kinematics(j0=90, j1=0, j2=0)
    assert p.x == pytest.approx(0.0, abs=1e-9)
    assert p.y == pytest.approx(L1 + L2 + L_TOOL, abs=1e-9)
    assert p.z == pytest.approx(H_BASE, abs=1e-9)


def test_fk_j3_does_not_affect_position():
    """Wrist rotation is independent of tip XYZ under our convention."""
    p_no_wrist = forward_kinematics(0, 30, -10, j3=0)
    p_wrist = forward_kinematics(0, 30, -10, j3=70)
    assert p_no_wrist == p_wrist


# ---------------------------------------------------------------------------
# IK on hand-picked targets
# ---------------------------------------------------------------------------


def test_ik_fully_extended_horizontal():
    a = inverse_kinematics(L1 + L2 + L_TOOL, 0.0, H_BASE)
    assert a.j0 == pytest.approx(0.0, abs=1e-6)
    assert a.j1 == pytest.approx(0.0, abs=1e-3)
    assert a.j2 == pytest.approx(0.0, abs=1e-3)
    assert a.j3 == pytest.approx(0.0, abs=1e-9)


def test_ik_straight_up():
    """Tip directly above base at full vertical reach -> j1=j2=90."""
    a = inverse_kinematics(L_TOOL, 0.0, H_BASE + L1 + L2)
    assert a.j0 == pytest.approx(0.0, abs=1e-6)
    assert a.j1 == pytest.approx(90.0, abs=1e-3)
    assert a.j2 == pytest.approx(90.0, abs=1e-3)


def test_ik_passes_wrist_through():
    a = inverse_kinematics(250.0, 0.0, 50.0, wrist=42.5)
    assert a.j3 == pytest.approx(42.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Workspace / joint limit error cases
# ---------------------------------------------------------------------------


def test_ik_unreachable_too_far_raises():
    # Far beyond L1+L2+L_TOOL = 356 mm.
    with pytest.raises(WorkspaceError, match="max reach"):
        inverse_kinematics(500.0, 0.0, H_BASE)


def test_ik_unreachable_dead_zone_raises():
    # Place wrist at (0, 0) in plane, well inside the |L1-L2|=16mm dead zone.
    with pytest.raises(WorkspaceError, match="min reach"):
        inverse_kinematics(L_TOOL, 0.0, H_BASE)


def test_ik_joint_limit_violation_raises():
    # A central target whose elbow-up solution violates the parallelogram
    # coupling: j1 ~ 67°, j2 ~ -56°, floor 2*67 - 180 = -46° → j2 < floor.
    with pytest.raises(JointLimitError, match="parallelogram"):
        inverse_kinematics(200.0, 0.0, H_BASE)


def test_ik_j0_limit_violation_raises():
    # Target behind the base requires j0 outside [-90, 90].
    with pytest.raises(JointLimitError, match="j0"):
        inverse_kinematics(-200.0, 0.0, H_BASE + 50.0)


def test_in_workspace_true_for_reachable():
    assert in_workspace(250.0, 0.0, 50.0) is True


def test_in_workspace_false_for_far():
    assert in_workspace(500.0, 0.0, H_BASE) is False


def test_in_workspace_false_for_limit_violation():
    assert in_workspace(200.0, 0.0, H_BASE) is False  # parallelogram floor


# ---------------------------------------------------------------------------
# FK/IK round-trip — property test
# ---------------------------------------------------------------------------

# Generate joint configurations strictly inside all limits (with margin),
# FK them to a Cartesian target, then IK back and verify joint recovery.

_J0_LO, _J0_HI = J0_LIMITS
_J1_LO, _J1_HI = J1_LIMITS
_J2_LO, _J2_HI = J2_LIMITS
_J3_LO, _J3_HI = J3_LIMITS


def _joint_strategy():
    # Cap j1 at 90° so the upper arm never swings past vertical — past-vertical
    # configs put the wrist in the -X hemisphere, which on this arm is a
    # j0=±180° solution that's outside the [-90°, 90°] j0 limit (the IK would
    # legitimately reject it, but it's not a round-trip failure).
    return st.tuples(
        st.floats(min_value=_J0_LO + 1.0, max_value=_J0_HI - 1.0),
        st.floats(min_value=_J1_LO + 1.0, max_value=90.0),
        st.floats(min_value=_J2_LO + 1.0, max_value=_J2_HI - 1.0),
        st.floats(min_value=_J3_LO + 1.0, max_value=_J3_HI - 1.0),
    )


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)
@given(_joint_strategy())
def test_fk_ik_roundtrip(joints):
    j0, j1, j2, j3 = joints
    # Elbow-up requires j1 > j2 (upper arm aimed higher than forearm). Keep
    # margin from both singularities: j1≈j2 (arm fully extended, α→π) and
    # j1−j2≈180 (arm folded back, α→0).
    assume(j1 - j2 > 2.0)
    assume(j1 - j2 < 178.0)
    # Respect parallelogram coupling with margin.
    assume(j2 > parallelogram_floor_deg(j1) + 5.0)
    # Keep the wrist away from r ≈ 0 (where atan2 of (x, y) becomes ill-defined
    # for j0 recovery).
    pos = forward_kinematics(j0, j1, j2, j3)
    if math.hypot(pos.x, pos.y) < L_TOOL + 5.0:
        assume(False)

    recovered = inverse_kinematics(pos.x, pos.y, pos.z, wrist=j3)

    assert recovered.j0 == pytest.approx(j0, abs=1e-4)
    assert recovered.j1 == pytest.approx(j1, abs=1e-4)
    assert recovered.j2 == pytest.approx(j2, abs=1e-4)
    assert recovered.j3 == pytest.approx(j3, abs=1e-9)

    # And the position itself round-trips to within 0.1 mm (spec target).
    pos2 = forward_kinematics(*recovered)
    dx = pos.x - pos2.x
    dy = pos.y - pos2.y
    dz = pos.z - pos2.z
    assert math.sqrt(dx * dx + dy * dy + dz * dz) < 0.1


# ---------------------------------------------------------------------------
# Boundary: exact maximum reach
# ---------------------------------------------------------------------------


def test_ik_at_max_reach_within_tolerance():
    """Place tip exactly at maximum extension — should succeed at the edge."""
    target_r = L1 + L2 + L_TOOL
    a = inverse_kinematics(target_r, 0.0, H_BASE)
    assert a.j1 == pytest.approx(0.0, abs=1e-3)
    assert a.j2 == pytest.approx(0.0, abs=1e-3)


def test_ik_just_past_max_reach_raises():
    target_r = L1 + L2 + L_TOOL + 1.0
    with pytest.raises(WorkspaceError):
        inverse_kinematics(target_r, 0.0, H_BASE)


# ---------------------------------------------------------------------------
# NamedTuple sanity (cheap, but cheap insurance against accidental refactors)
# ---------------------------------------------------------------------------


def test_jointangles_is_tuple_of_floats():
    a = JointAngles(1.0, 2.0, 3.0, 4.0)
    assert tuple(a) == (1.0, 2.0, 3.0, 4.0)


def test_position_is_tuple_of_floats():
    p = Position(1.0, 2.0, 3.0)
    assert tuple(p) == (1.0, 2.0, 3.0)
