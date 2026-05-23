"""Tests for arm.py — UArm class against SimulatedBus."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from arm import HOME_JOINTS, UArm
from hardware import SimulatedBus
from kinematics import JointLimitError, Position, WorkspaceError, forward_kinematics


@pytest.fixture()
def bus() -> SimulatedBus:
    return SimulatedBus()


@pytest.fixture()
def arm(bus: SimulatedBus) -> UArm:
    a = UArm(bus=bus)
    a.connect()
    yield a
    a.disconnect()


# ------------------------------------------------------------------
# Home
# ------------------------------------------------------------------


def test_home_reaches_home_pose(arm: UArm) -> None:
    arm.home(blocking=True)
    a = arm.get_joint_angles()
    assert a.j0 == pytest.approx(HOME_JOINTS.j0, abs=1.0)
    assert a.j1 == pytest.approx(HOME_JOINTS.j1, abs=1.0)
    assert a.j2 == pytest.approx(HOME_JOINTS.j2, abs=1.0)
    assert a.j3 == pytest.approx(HOME_JOINTS.j3, abs=1.0)


def test_home_uses_slow_speed(bus: SimulatedBus) -> None:
    arm = UArm(bus=bus)
    arm.connect()
    t0 = time.monotonic()
    arm.home(blocking=True)
    elapsed = time.monotonic() - t0
    # Home from (0,0,0,0) to (0,45,-45,0): max delta is 45 deg at 30 deg/s → ~1.5s
    assert elapsed >= 1.0
    arm.disconnect()


# ------------------------------------------------------------------
# Joint-space motion
# ------------------------------------------------------------------


def test_set_joint_angles_blocking(arm: UArm) -> None:
    arm.set_joint_angles(10, 60, -30, 5, blocking=True)
    a = arm.get_joint_angles()
    assert a.j0 == pytest.approx(10.0, abs=0.5)
    assert a.j1 == pytest.approx(60.0, abs=0.5)
    assert a.j2 == pytest.approx(-30.0, abs=0.5)
    assert a.j3 == pytest.approx(5.0, abs=0.5)


def test_set_joint_angles_round_trip(arm: UArm) -> None:
    arm.set_joint_angles(0, 45, -45, 0, blocking=True)
    pos = arm.get_position()
    expected = forward_kinematics(0, 45, -45, 0)
    assert pos.x == pytest.approx(expected.x, abs=0.5)
    assert pos.y == pytest.approx(expected.y, abs=0.5)
    assert pos.z == pytest.approx(expected.z, abs=0.5)


# ------------------------------------------------------------------
# Cartesian motion
# ------------------------------------------------------------------


def test_set_position_blocking(arm: UArm) -> None:
    arm.set_position(250, 0, 50, blocking=True)
    pos = arm.get_position()
    assert pos.x == pytest.approx(250.0, abs=1.5)
    assert pos.y == pytest.approx(0.0, abs=1.5)
    assert pos.z == pytest.approx(50.0, abs=1.5)


def test_get_position_matches_set(arm: UArm) -> None:
    arm.set_position(250, 50, 100, blocking=True)
    pos = arm.get_position()
    assert pos.x == pytest.approx(250.0, abs=1.0)
    assert pos.y == pytest.approx(50.0, abs=1.0)
    assert pos.z == pytest.approx(100.0, abs=1.0)


def test_set_position_workspace_error(arm: UArm) -> None:
    with pytest.raises(WorkspaceError, match="max reach"):
        arm.set_position(500, 0, 80)


def test_set_position_joint_limit_error(arm: UArm) -> None:
    with pytest.raises(JointLimitError, match="parallelogram"):
        arm.set_position(200, 0, 80)


# ------------------------------------------------------------------
# move_along
# ------------------------------------------------------------------


def test_move_along_visits_each_waypoint(arm: UArm) -> None:
    waypoints = [(250, 0, 50), (280, 0, 80), (260, 30, 60)]
    visited: list[Position] = []

    def _capture(pos: Position) -> None:
        visited.append(pos)

    arm.on_position(_capture)
    arm.move_along(waypoints, wrist=0.0)
    arm.wait_for_idle(timeout=10.0)

    # After move_along completes, arm should be at last waypoint
    pos = arm.get_position()
    assert pos.x == pytest.approx(260.0, abs=1.0)
    assert pos.y == pytest.approx(30.0, abs=1.0)
    assert pos.z == pytest.approx(60.0, abs=1.0)

    # Position callbacks should have fired during the slew
    assert len(visited) > 0


def test_move_along_propagates_ik_error(arm: UArm) -> None:
    waypoints = [(250, 0, 50), (500, 0, 80)]  # second point unreachable
    with pytest.raises(WorkspaceError):
        arm.move_along(waypoints)


# ------------------------------------------------------------------
# Position callback
# ------------------------------------------------------------------


def test_position_callback_fires_during_slew(arm: UArm) -> None:
    positions: list[Position] = []

    def _cb(pos: Position) -> None:
        positions.append(pos)

    arm.on_position(_cb)
    arm.set_joint_angles(0, 45, -45, 0, blocking=True)

    # Callbacks should have been fired multiple times during the slew
    assert len(positions) > 1


# ------------------------------------------------------------------
# wait_for_idle
# ------------------------------------------------------------------


def test_wait_for_idle_returns_true(arm: UArm) -> None:
    arm.set_joint_angles(0, 30, -20, 0)
    result = arm.wait_for_idle(timeout=10.0)
    assert result is True


def test_wait_for_idle_timeout_returns_false(arm: UArm) -> None:
    arm._bus.set_speed(0.1)  # very slow
    arm.set_joint_angles(0, 90, -90, 0)
    result = arm.wait_for_idle(timeout=0.1)
    assert result is False


# ------------------------------------------------------------------
# Recording / replay
# ------------------------------------------------------------------


def test_recording_produces_json(
    arm: UArm, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("arm.RECORDINGS_DIR", tmp_path)
    arm.set_joint_angles(0, 45, -45, 0, blocking=True)
    arm.record_start("test_rec")
    time.sleep(0.15)  # ~3 frames at 20Hz
    path = arm.record_stop()

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "test_rec"
    assert len(data["frames"]) >= 2
    frame = data["frames"][0]
    assert "t" in frame
    assert "j0" in frame and "j1" in frame and "j2" in frame and "j3" in frame


def test_replay_reaches_recorded_positions(
    arm: UArm, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("arm.RECORDINGS_DIR", tmp_path)

    # Record a move
    arm.set_joint_angles(0, 30, -20, 0, blocking=True)
    arm.record_start("replay_test")
    arm.set_joint_angles(0, 60, -40, 0, blocking=True)
    time.sleep(0.1)
    path = arm.record_stop()

    # Reset to origin
    arm.set_joint_angles(0, 0, 0, 0, blocking=True)

    # Replay
    arm.replay(path, speed_factor=5.0, blocking=True)
    a = arm.get_joint_angles()
    # Should end near the last recorded position (j1≈60, j2≈-40)
    assert a.j1 == pytest.approx(60.0, abs=2.0)
    assert a.j2 == pytest.approx(-40.0, abs=2.0)


# ------------------------------------------------------------------
# Disconnect
# ------------------------------------------------------------------


def test_disconnect_joins_bus_thread() -> None:
    bus = SimulatedBus()
    arm = UArm(bus=bus)
    arm.connect()
    arm.set_joint_angles(0, 10, -10, 0)
    time.sleep(0.05)
    arm.disconnect()
    # Bus thread should be stopped
    assert bus._thread is None or not bus._thread.is_alive()


# ------------------------------------------------------------------
# Actuator stubs
# ------------------------------------------------------------------


def test_set_pump_sends_to_bus(arm: UArm, bus: SimulatedBus) -> None:
    arm.set_pump(True)
    assert bus.get_angle(4) == pytest.approx(90.0, abs=1.0)
    arm.set_pump(False)
    assert bus.get_angle(4) == pytest.approx(0.0, abs=1.0)


def test_set_gripper_sends_to_bus(arm: UArm, bus: SimulatedBus) -> None:
    arm.set_gripper(True)
    assert bus.get_angle(5) == pytest.approx(90.0, abs=1.0)
    arm.set_gripper(False)
    assert bus.get_angle(5) == pytest.approx(0.0, abs=1.0)
