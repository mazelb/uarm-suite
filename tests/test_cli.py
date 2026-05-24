"""Tests for cli.py — Typer CLI against SimulatedBus."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _sim_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UARM_MODE", "sim")


# ------------------------------------------------------------------
# where
# ------------------------------------------------------------------


def test_where_shows_position() -> None:
    result = runner.invoke(app, ["where"])
    assert result.exit_code == 0
    assert "Position:" in result.stdout
    assert "Joints:" in result.stdout


# ------------------------------------------------------------------
# home
# ------------------------------------------------------------------


def test_home_prints_position() -> None:
    result = runner.invoke(app, ["home"])
    assert result.exit_code == 0
    assert "Homed to" in result.stdout
    assert "Joints:" in result.stdout


# ------------------------------------------------------------------
# goto (success)
# ------------------------------------------------------------------


def test_goto_success() -> None:
    result = runner.invoke(app, ["goto", "250", "0", "50"])
    assert result.exit_code == 0
    assert "Reached" in result.stdout


def test_goto_with_negative_coord() -> None:
    result = runner.invoke(app, ["goto", "250", "-50", "50"])
    assert result.exit_code == 0
    assert "Reached" in result.stdout


# ------------------------------------------------------------------
# goto (error paths)
# ------------------------------------------------------------------


def test_goto_workspace_error() -> None:
    result = runner.invoke(app, ["goto", "500", "0", "80"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "max reach" in result.output


def test_goto_joint_limit_error() -> None:
    result = runner.invoke(app, ["goto", "200", "0", "80"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "parallelogram" in result.output


# ------------------------------------------------------------------
# joints
# ------------------------------------------------------------------


def test_joints_success() -> None:
    result = runner.invoke(app, ["joints", "0", "60", "-30", "0"])
    assert result.exit_code == 0
    assert "Joints:" in result.stdout
    assert "Position:" in result.stdout


# ------------------------------------------------------------------
# list / play (with pre-created recording)
# ------------------------------------------------------------------


@pytest.fixture()
def recordings_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("arm.RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr("cli.RECORDINGS_DIR", tmp_path)
    return tmp_path


def _write_recording(directory: Path, name: str) -> Path:
    path = directory / f"{name}.json"
    data = {
        "name": name,
        "frames": [
            {"t": 0.0, "j0": 0.0, "j1": 0.0, "j2": 0.0, "j3": 0.0},
            {"t": 0.05, "j0": 0.0, "j1": 1.0, "j2": -1.0, "j3": 0.0},
            {"t": 0.10, "j0": 0.0, "j1": 2.0, "j2": -2.0, "j3": 0.0},
        ],
    }
    path.write_text(json.dumps(data))
    return path


def test_list_shows_recordings(recordings_dir: Path) -> None:
    _write_recording(recordings_dir, "demo")
    _write_recording(recordings_dir, "test2")
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert "test2" in result.stdout


def test_list_empty(recordings_dir: Path) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No recordings found" in result.stdout


def test_play_success(recordings_dir: Path) -> None:
    _write_recording(recordings_dir, "demo")
    result = runner.invoke(app, ["play", "demo"])
    assert result.exit_code == 0
    assert "Replay complete" in result.stdout


def test_play_not_found(recordings_dir: Path) -> None:
    result = runner.invoke(app, ["play", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ------------------------------------------------------------------
# record (programmatic — Ctrl-C cannot be tested via CliRunner)
# ------------------------------------------------------------------


def test_record_creates_file(recordings_dir: Path) -> None:
    """Test recording via the arm API since CliRunner can't send Ctrl-C."""
    import time

    from arm import UArm
    from hardware import SimulatedBus

    bus = SimulatedBus()
    arm = UArm(bus=bus)
    arm.connect()
    try:
        arm.record_start("cli_rec")
        time.sleep(0.15)
        path = arm.record_stop()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "cli_rec"
        assert len(data["frames"]) >= 2
    finally:
        arm.disconnect()


# ------------------------------------------------------------------
# shell
# ------------------------------------------------------------------


def test_shell_launches() -> None:
    with patch("cli.code") as mock_code:
        mock_code.interact.return_value = None
        result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mock_code.interact.assert_called_once()
        call_kwargs = mock_code.interact.call_args
        assert "arm" in call_kwargs.kwargs.get("local", call_kwargs[1].get("local", {}))


# ------------------------------------------------------------------
# server detection
# ------------------------------------------------------------------


def test_where_uses_server_when_available() -> None:
    with (
        patch("cli._server_running", return_value=True),
        patch("cli._get_json") as mock_get,
    ):
        mock_get.return_value = {
            "j0": 0.0,
            "j1": 45.0,
            "j2": -45.0,
            "j3": 0.0,
            "x": 268.1,
            "y": 0.0,
            "z": 68.7,
        }
        result = runner.invoke(app, ["where"])
        assert result.exit_code == 0
        assert "268.1" in result.stdout
        mock_get.assert_called_once_with("/api/state")
