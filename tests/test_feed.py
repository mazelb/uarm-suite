"""Tests for Phase 8B — straight-line moves at a Cartesian feed rate.

Covers kinematics.interpolate_line, UArm.move_linear (straightness, refusal
before motion, pacing), feed selection in activities._draw.draw_strokes, and
the feed fields' persistence + `uarm pen` CLI plumbing.
"""

from __future__ import annotations

import math
import time

import pytest
from typer.testing import CliRunner

import activities._draw as _draw
import drawing
from arm import UArm
from cli import app
from drawing import DrawingConfig, load_drawing_config, save_drawing_config
from hardware import SimulatedBus
from kinematics import (
    JointLimitError,
    WorkspaceError,
    forward_kinematics,
    interpolate_line,
)

runner = CliRunner()

_JOINT_CHANNELS = (0, 1, 2, 3)


# ---------------------------------------------------------------------------
# interpolate_line (pure)
# ---------------------------------------------------------------------------


def test_interpolate_spacing_and_endpoints() -> None:
    p0, p1 = (200.0, -50.0, 10.0), (260.0, 70.0, 40.0)
    pts = interpolate_line(p0, p1, 2.0)
    assert pts[-1] == p1  # exact, no float accumulation
    assert p0 not in pts
    prev = p0
    for p in pts:
        assert math.dist(prev, p) <= 2.0 + 1e-9
        prev = p
    # All points on the segment: distance from line is ~0.
    seg = tuple(b - a for a, b in zip(p0, p1, strict=True))
    seg_len = math.dist(p0, p1)
    for p in pts:
        v = tuple(c - a for a, c in zip(p0, p, strict=True))
        t = sum(a * b for a, b in zip(v, seg, strict=True)) / (seg_len * seg_len)
        foot = tuple(a + t * s for a, s in zip(p0, seg, strict=True))
        assert math.dist(p, foot) < 1e-9


def test_interpolate_zero_length_yields_endpoint() -> None:
    p = (250.0, 0.0, 50.0)
    assert interpolate_line(p, p, 2.0) == [p]


def test_interpolate_rejects_bad_step() -> None:
    with pytest.raises(ValueError):
        interpolate_line((0, 0, 0), (1, 1, 1), 0.0)


# ---------------------------------------------------------------------------
# UArm.move_linear
# ---------------------------------------------------------------------------


@pytest.fixture()
def fast_arm(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 100000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 100000.0)
    bus = SimulatedBus(max_deg_per_sec=100000.0)
    arm = UArm(bus=bus).connect()
    arm.home(blocking=True)
    yield arm, bus
    arm.disconnect()


def _commanded_tips(bus: SimulatedBus, since: int) -> list[tuple[float, float, float]]:
    """FK of every full 4-joint target commanded after index ``since``."""
    cmds = [c for c in bus.commands[since:] if c["channel"] in _JOINT_CHANNELS]
    tips = []
    for i in range(0, len(cmds) - 3, 4):
        group = cmds[i : i + 4]
        assert [c["channel"] for c in group] == list(_JOINT_CHANNELS)
        pos = forward_kinematics(*(c["degrees"] for c in group))
        tips.append((pos.x, pos.y, pos.z))
    return tips


def test_move_linear_commands_straight_path(fast_arm) -> None:
    arm, bus = fast_arm
    arm.set_position(250.0, -60.0, 40.0, blocking=True)
    mark = len(bus.commands)
    arm.move_linear(250.0, 60.0, 40.0, feed=1e6)

    tips = _commanded_tips(bus, mark)
    assert len(tips) == math.ceil(120.0 / 2.0)  # default DRAW_STEP_MM
    assert tips[-1] == pytest.approx((250.0, 60.0, 40.0), abs=0.2)
    for x, y, z in tips:  # every commanded tip lies on the segment
        assert x == pytest.approx(250.0, abs=0.2)
        assert z == pytest.approx(40.0, abs=0.2)
        assert -60.0 - 0.2 <= y <= 60.0 + 0.2


def test_move_linear_unreachable_refuses_before_motion(fast_arm) -> None:
    arm, bus = fast_arm
    arm.set_position(250.0, 0.0, 40.0, blocking=True)
    mark = len(bus.commands)
    # A midpoint or the endpoint violates a limit — either way, refuse first.
    with pytest.raises((WorkspaceError, JointLimitError)):
        arm.move_linear(400.0, 0.0, 40.0, feed=1e6)  # beyond max reach
    assert len(bus.commands) == mark  # nothing was commanded

    with pytest.raises(ValueError):
        arm.move_linear(250.0, 10.0, 40.0, feed=0.0)
    assert len(bus.commands) == mark


def test_move_linear_paces_at_feed(fast_arm) -> None:
    arm, _ = fast_arm
    arm.set_position(200.0, 0.0, 50.0, blocking=True)
    t0 = time.monotonic()
    arm.move_linear(260.0, 0.0, 50.0, feed=120.0)  # 60 mm at 120 mm/s → ≥ 0.5 s
    elapsed = time.monotonic() - t0
    assert 0.45 <= elapsed < 3.0


# ---------------------------------------------------------------------------
# draw_strokes feed selection
# ---------------------------------------------------------------------------


class FeedArm:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[float, float, float], float]] = []

    def move_linear(self, x, y, z, *, wrist=0.0, feed, step_mm=None):
        self.calls.append(((x, y, z), feed))


def test_draw_strokes_uses_draw_and_travel_feeds() -> None:
    arm = FeedArm()
    _draw.draw_strokes(
        arm,
        [[(240.0, 0.0), (260.0, 0.0)]],
        table_z=0.0,
        pen_up_z=20.0,
        feed=33.0,
        travel_feed=77.0,
    )
    assert [c[0] for c in arm.calls] == [
        (240.0, 0.0, 20.0),  # approach above the start
        (240.0, 0.0, 0.0),  # pen down
        (260.0, 0.0, 0.0),  # draw
        (260.0, 0.0, 20.0),  # pen up
    ]
    # Travel feed for the approach and lift; draw feed for lowering + drawing.
    assert [c[1] for c in arm.calls] == [77.0, 33.0, 33.0, 77.0]


def test_draw_strokes_defaults_resolve_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_draw, "DRAW_FEED_MM_S", 11.0)
    monkeypatch.setattr(_draw, "TRAVEL_FEED_MM_S", 22.0)
    arm = FeedArm()
    _draw.draw_strokes(arm, [[(240.0, 0.0), (260.0, 0.0)]], table_z=0.0, pen_up_z=20.0)
    assert [c[1] for c in arm.calls] == [22.0, 11.0, 11.0, 22.0]


# ---------------------------------------------------------------------------
# Persistence + CLI
# ---------------------------------------------------------------------------


def test_feed_fields_default_to_none_and_round_trip() -> None:
    assert DrawingConfig().feed is None
    assert DrawingConfig().travel_feed is None
    save_drawing_config(DrawingConfig(feed=60.0, travel_feed=150.0))
    cfg = load_drawing_config()
    assert cfg.feed == 60.0
    assert cfg.travel_feed == 150.0


def test_pen_set_and_show_feeds() -> None:
    result = runner.invoke(app, ["pen", "set", "--feed", "60", "--travel-feed", "150"])
    assert result.exit_code == 0
    cfg = load_drawing_config()
    assert cfg.feed == 60.0
    assert cfg.travel_feed == 150.0
    assert "60.0 mm/s" in result.stdout
    assert "150.0 mm/s" in result.stdout


def test_pen_show_marks_suite_defaults() -> None:
    assert not drawing.DRAWING_PATH.exists()
    result = runner.invoke(app, ["pen", "show"])
    assert result.exit_code == 0
    assert "suite default" in result.stdout
