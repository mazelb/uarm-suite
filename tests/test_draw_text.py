"""Tests for the draw-text activity (Phase 8C)."""

from __future__ import annotations

import pytest

import activities
from activities.draw_text import (
    _GLYPHS,
    GLYPH_H,
    GLYPH_W,
    DrawText,
    text_strokes,
)
from kinematics import in_workspace


def test_registered_as_runnable():
    activities.discover()
    listed = {a["slug"]: a for a in activities.list_activities()}
    assert "draw-text" in listed
    assert listed["draw-text"]["interactive"] is False


def test_glyphs_stay_inside_their_cell():
    # Slight slack for the comma descender and dot ticks.
    for ch, strokes in _GLYPHS.items():
        for stroke in strokes:
            assert len(stroke) >= 2, f"{ch!r} has a degenerate stroke"
            for gx, gy in stroke:
                assert -0.5 <= gx <= GLYPH_W + 0.5, f"{ch!r} x={gx} outside cell"
                assert -1.0 <= gy <= GLYPH_H + 0.5, f"{ch!r} y={gy} outside cell"


def test_text_strokes_centered_and_scaled():
    size = 30.0
    strokes = text_strokes("HI", size, 250.0, 0.0)
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    # Cap height maps to X (page "up" is +X), centered on center_x.
    assert min(xs) == pytest.approx(250.0 - size / 2)
    assert max(xs) == pytest.approx(250.0 + size / 2)
    # Cell-centered laterally: total width is 2 cells + 1 gap = 10 units = 50 mm,
    # and H's ink starts exactly at the left cell edge (+25). I's ink stops a
    # unit short of its cell edge, so we bound rather than mirror.
    u = size / GLYPH_H
    assert max(ys) == pytest.approx(25.0)  # H starts at gx=0
    assert min(ys) >= -25.0 - 1e-9  # all ink inside the string box
    assert min(ys) == pytest.approx(-25.0 + u)  # I's rightmost ink at gx=3


def test_text_advances_right_toward_minus_y():
    a1 = text_strokes("A", 30.0, 250.0, 0.0)
    a2 = text_strokes("AA", 30.0, 250.0, 0.0)
    # In "AA" the two glyphs are offset by one advance along -Y.
    u = 30.0 / GLYPH_H
    advance = (GLYPH_W + 2.0) * u
    first_y = max(y for s in a2 for _, y in s)
    second = [s for s in a2[len(a1) :]]
    second_y = max(y for s in second for _, y in s)
    assert first_y - second_y == pytest.approx(advance)


def test_space_advances_without_strokes():
    with_space = text_strokes("A A", 30.0, 250.0, 0.0)
    without = text_strokes("AA", 30.0, 250.0, 0.0)
    assert len(with_space) == len(without)  # space adds no strokes

    def width(strokes):
        ys = [y for s in strokes for _, y in s]
        return max(ys) - min(ys)

    assert width(with_space) > width(without)  # ...but does take up room


def test_lowercase_is_uppercased():
    assert text_strokes("hi", 30.0, 250.0, 0.0) == text_strokes("HI", 30.0, 250.0, 0.0)


def test_unsupported_chars_raise():
    with pytest.raises(ValueError, match="unsupported character"):
        text_strokes("HÉLLO", 30.0, 250.0, 0.0)
    with pytest.raises(ValueError, match="size must be positive"):
        text_strokes("HI", 0.0, 250.0, 0.0)
    assert text_strokes("", 30.0, 250.0, 0.0) == []


def test_default_placement_reachable():
    strokes = text_strokes("HI!", 30.0, 250.0, 0.0)
    for stroke in strokes:
        for x, y in stroke:
            for z in (0.0, 20.0):
                assert in_workspace(x, y, z), f"point ({x:.1f},{y:.1f},{z:.1f}) unreachable"


class FakeArm:
    def __init__(self):
        self.positions = []
        self.feeds = []
        self.homed = False

    def move_linear(self, x, y, z, *, wrist=0.0, feed, step_mm=None):
        self.positions.append((x, y, z))
        self.feeds.append(feed)

    def home(self, blocking=True):
        self.homed = True


def test_configure_and_run_records_moves():
    arm = FakeArm()
    act = DrawText()
    act.configure({"text": "OK", "size": 25.0, "center_y": 40.0, "feed": 33.0})
    assert act.text == "OK"
    act.setup(arm)
    act.run(arm)
    assert arm.homed is True
    assert len(arm.positions) > 0
    assert 33.0 in arm.feeds  # configured draw feed reached the motion layer
    zs = {z for _, _, z in arm.positions}
    assert zs == {0.0, 20.0}  # pen-down at table_z, lifts at pen_up_z
