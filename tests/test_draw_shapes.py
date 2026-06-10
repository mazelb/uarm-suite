"""Tests for the draw-shapes activity (Phase 7D)."""

from __future__ import annotations

import pytest

import activities
from activities.draw_shapes import SHAPES, DrawShapes, shape_strokes
from kinematics import in_workspace


def test_registered_as_runnable():
    activities.discover()
    listed = {a["slug"]: a for a in activities.list_activities()}
    assert "draw-shapes" in listed
    assert listed["draw-shapes"]["interactive"] is False


@pytest.mark.parametrize("shape", SHAPES)
def test_shape_paths_closed_and_reachable(shape):
    strokes = shape_strokes(shape, size=40.0, center_x=250.0, center_y=0.0)
    assert strokes
    for stroke in strokes:
        assert stroke[0] == stroke[-1]  # closed loop
        for x, y in stroke:
            for z in (0.0, 20.0):
                assert in_workspace(x, y, z), f"{shape} point ({x:.1f},{y:.1f},{z:.1f}) unreachable"


def test_unknown_shape_raises():
    with pytest.raises(ValueError):
        shape_strokes("hexagon", 40.0, 250.0, 0.0)


class FakeArm:
    def __init__(self):
        self.positions = []
        self.feeds = []  # feed passed with each move_linear, parallel to positions
        self.homed = False

    def set_position(self, x, y, z, *, wrist=0.0, speed=None, blocking=False):
        self.positions.append((x, y, z))

    def move_linear(self, x, y, z, *, wrist=0.0, feed, step_mm=None):
        self.positions.append((x, y, z))
        self.feeds.append(feed)

    def home(self, blocking=True):
        self.homed = True


def test_configure_and_run_records_moves():
    arm = FakeArm()
    act = DrawShapes()
    act.configure({"shape": "triangle", "size": 30.0, "center_x": 240.0})
    assert act.shape == "triangle"
    assert act.size == 30.0
    assert act.center_x == 240.0
    act.setup(arm)
    act.run(arm)
    assert arm.homed is True
    assert len(arm.positions) > 0
