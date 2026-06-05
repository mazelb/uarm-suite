"""Tests for drawing.py and the `uarm pen` CLI (Phase 8A).

Config persistence, grid-corner reachability, the pen CLI commands, and the
activity auto-load wiring. The autouse `_isolate_drawing_config` fixture in
conftest.py points DRAWING_PATH at a per-test tmp file, so none of these touch
a real calibrated drawing.json.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import drawing
from cli import app
from drawing import (
    DrawingConfig,
    grid_corners,
    load_drawing_config,
    save_drawing_config,
    unreachable_corners,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fast_sim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sim bus, no server, and near-instant homing for the motion commands."""
    monkeypatch.setenv("UARM_MODE", "sim")
    monkeypatch.setattr("cli._server_running", lambda: False)
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 100000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 100000.0)


# ---------------------------------------------------------------------------
# DrawingConfig + persistence
# ---------------------------------------------------------------------------


def test_defaults_match_legacy_hardcoded() -> None:
    cfg = DrawingConfig()
    assert cfg.table_z == 0.0
    assert cfg.pen_up == 20.0
    assert cfg.pen_up_z == 20.0
    assert cfg.wrist == 0.0


def test_pen_up_z_tracks_table_z() -> None:
    cfg = DrawingConfig(table_z=-35.0, pen_up=15.0)
    assert cfg.pen_up_z == -20.0


def test_load_missing_returns_defaults() -> None:
    assert not drawing.DRAWING_PATH.exists()
    assert load_drawing_config() == DrawingConfig()


def test_save_load_round_trip() -> None:
    cfg = DrawingConfig(table_z=-32.5, pen_up=12.0, wrist=5.0, pen_label="Sharpie")
    path = save_drawing_config(cfg)
    assert path == drawing.DRAWING_PATH
    assert load_drawing_config() == cfg


def test_load_ignores_unknown_keys() -> None:
    drawing.DRAWING_PATH.write_text(json.dumps({"table_z": -10.0, "legacy_field": 99}))
    cfg = load_drawing_config()
    assert cfg.table_z == -10.0
    assert not hasattr(cfg, "legacy_field")


# ---------------------------------------------------------------------------
# Grid geometry helpers
# ---------------------------------------------------------------------------


def test_grid_corners_extent() -> None:
    corners = grid_corners(250.0, 0.0, 40.0)
    assert len(corners) == 4
    xs = {x for x, _ in corners}
    ys = {y for _, y in corners}
    assert xs == {190.0, 310.0}  # 250 +/- 1.5*40
    assert ys == {-60.0, 60.0}


def test_default_grid_reachable() -> None:
    corners = grid_corners(250.0, 0.0, 40.0)
    assert unreachable_corners(corners, 20.0) == []


def test_oversized_grid_reports_bad_corners() -> None:
    corners = grid_corners(250.0, 0.0, 120.0)
    bad = unreachable_corners(corners, 20.0)
    assert bad  # far corners fall outside reach
    assert all(x == 430.0 for x, _ in bad)


# ---------------------------------------------------------------------------
# pen CLI
# ---------------------------------------------------------------------------


def test_pen_show_defaults_when_no_file() -> None:
    result = runner.invoke(app, ["pen", "show"])
    assert result.exit_code == 0
    assert "table_z" in result.stdout
    assert "showing defaults" in result.stdout


def test_pen_set_persists_and_shows() -> None:
    result = runner.invoke(app, ["pen", "set", "--table-z", "-30", "--label", "fine tip"])
    assert result.exit_code == 0
    assert load_drawing_config().table_z == -30.0
    assert load_drawing_config().pen_label == "fine tip"
    assert "-30.0" in result.stdout


def test_pen_jog_corners_success() -> None:
    # Four corners -> four "[Enter] for next corner" prompts.
    result = runner.invoke(app, ["pen", "jog-corners"], input="\n\n\n\n")
    assert result.exit_code == 0
    assert "corner 4/4" in result.stdout
    assert "all four corners reached" in result.stdout


def test_pen_jog_corners_unreachable_refuses() -> None:
    result = runner.invoke(app, ["pen", "jog-corners", "--cell", "120"])
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_pen_calibrate_saves_table_z() -> None:
    # Start at default pen_up_z=20; one Enter lowers by step (2) to 18, then save.
    result = runner.invoke(app, ["pen", "calibrate"], input="\ns\n")
    assert result.exit_code == 0
    assert "Saved table_z = 18.0" in result.stdout
    assert load_drawing_config().table_z == 18.0


def test_pen_calibrate_quit_does_not_save() -> None:
    result = runner.invoke(app, ["pen", "calibrate"], input="q\n")
    assert result.exit_code == 0
    assert "nothing saved" in result.stdout.lower()
    assert not drawing.DRAWING_PATH.exists()


def test_pen_calibrate_unreachable_start_refuses() -> None:
    result = runner.invoke(app, ["pen", "calibrate", "--x", "600", "--start-z", "80"])
    assert result.exit_code == 1
    assert "outside the workspace" in result.output


# ---------------------------------------------------------------------------
# Activity auto-load wiring
# ---------------------------------------------------------------------------


def test_draw_shapes_picks_up_persisted_height() -> None:
    save_drawing_config(DrawingConfig(table_z=-28.0, pen_up=10.0, wrist=3.0))
    from activities.draw_shapes import DrawShapes

    act = DrawShapes()
    assert act.table_z == -28.0
    assert act.pen_up == 10.0
    assert act.wrist == 3.0


def test_tic_tac_toe_default_config_from_drawing() -> None:
    save_drawing_config(DrawingConfig(table_z=-25.0, pen_up=18.0))
    from activities.tic_tac_toe import default_grid_config

    cfg = default_grid_config()
    assert cfg.table_z == -25.0
    assert cfg.pen_up == 18.0
    assert cfg.pen_up_z == -7.0


def test_activity_options_override_persisted_height() -> None:
    save_drawing_config(DrawingConfig(table_z=-25.0))
    from activities.draw_shapes import DrawShapes

    act = DrawShapes()
    act.configure({"table_z": 5.0})
    assert act.table_z == 5.0
