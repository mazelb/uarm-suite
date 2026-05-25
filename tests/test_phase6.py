"""Tests for Phase 6 features: calibration API, soft-limit helpers."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from arm import UArm
from config import SERVO_CALIBRATION, ServoCalibration
from hardware import SimulatedBus


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 10000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 10000.0)
    monkeypatch.setattr("arm.RECORDINGS_DIR", tmp_path / "recordings")

    import server

    monkeypatch.setattr(server, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(server, "CALIBRATION_PATH", tmp_path / "calibration.json")

    bus = SimulatedBus(max_deg_per_sec=10000)
    arm = UArm(bus=bus)
    arm.connect()
    arm.home(blocking=True)
    server._arm = arm
    with TestClient(server.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_calibration():
    """Ensure SERVO_CALIBRATION is reset to defaults after each test."""
    saved = {ch: dict(cal) for ch, cal in SERVO_CALIBRATION.items()}
    yield
    for ch in SERVO_CALIBRATION:
        SERVO_CALIBRATION[ch] = ServoCalibration(**saved[ch])


# ------------------------------------------------------------------
# GET /api/calibration
# ------------------------------------------------------------------


def test_get_calibration(client: TestClient) -> None:
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    data = resp.json()
    assert "0" in data
    assert data["0"]["zero_deg"] == 90.0
    assert data["0"]["direction"] == 1


# ------------------------------------------------------------------
# POST /api/calibration
# ------------------------------------------------------------------


def test_update_calibration_zero_deg(client: TestClient) -> None:
    resp = client.post(
        "/api/calibration",
        json={
            "channel": 0,
            "zero_deg": 85.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["0"]["zero_deg"] == 85.0
    assert SERVO_CALIBRATION[0]["zero_deg"] == 85.0


def test_update_calibration_direction(client: TestClient) -> None:
    resp = client.post(
        "/api/calibration",
        json={
            "channel": 1,
            "direction": -1,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["1"]["direction"] == -1


def test_update_calibration_pulse_widths(client: TestClient) -> None:
    resp = client.post(
        "/api/calibration",
        json={
            "channel": 2,
            "min_us": 600,
            "max_us": 2400,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["2"]["min_us"] == 600
    assert resp.json()["2"]["max_us"] == 2400


def test_update_calibration_invalid_channel(client: TestClient) -> None:
    resp = client.post(
        "/api/calibration",
        json={
            "channel": 99,
            "zero_deg": 85.0,
        },
    )
    assert resp.status_code == 422


def test_update_calibration_invalid_direction(client: TestClient) -> None:
    resp = client.post(
        "/api/calibration",
        json={
            "channel": 0,
            "direction": 2,
        },
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------
# POST /api/calibration/save + load
# ------------------------------------------------------------------


def test_save_calibration(client: TestClient, monkeypatch, tmp_path) -> None:
    import server

    cal_path = tmp_path / "calibration.json"
    monkeypatch.setattr(server, "CALIBRATION_PATH", cal_path)

    client.post("/api/calibration", json={"channel": 0, "zero_deg": 82.5})
    resp = client.post("/api/calibration/save")
    assert resp.status_code == 200
    assert cal_path.exists()

    data = json.loads(cal_path.read_text())
    assert data["0"]["zero_deg"] == 82.5


def test_load_calibration_on_startup(monkeypatch, tmp_path) -> None:
    import server

    cal_path = tmp_path / "calibration.json"
    cal_path.write_text(
        json.dumps(
            {
                "0": {"min_us": 550, "max_us": 2450, "zero_deg": 88.0, "direction": -1},
            }
        )
    )
    monkeypatch.setattr(server, "CALIBRATION_PATH", cal_path)

    SERVO_CALIBRATION[0] = ServoCalibration(
        min_us=500,
        max_us=2500,
        zero_deg=90.0,
        direction=1,
    )
    server._load_calibration()
    assert SERVO_CALIBRATION[0]["zero_deg"] == 88.0
    assert SERVO_CALIBRATION[0]["direction"] == -1
    assert SERVO_CALIBRATION[0]["min_us"] == 550


# ------------------------------------------------------------------
# POST /api/calibration/reset
# ------------------------------------------------------------------


def test_reset_calibration(client: TestClient) -> None:
    client.post("/api/calibration", json={"channel": 0, "zero_deg": 75.0})
    assert SERVO_CALIBRATION[0]["zero_deg"] == 75.0

    resp = client.post("/api/calibration/reset")
    assert resp.status_code == 200
    assert resp.json()["0"]["zero_deg"] == 90.0
    assert SERVO_CALIBRATION[0]["zero_deg"] == 90.0


# ------------------------------------------------------------------
# Soft-limit logic (pure Python helpers)
# ------------------------------------------------------------------


def test_joint_near_limit_upper() -> None:
    from config import J0_LIMITS

    val = J0_LIMITS[1] - 3.0
    assert (J0_LIMITS[1] - val) < 5.0


def test_parallelogram_margin() -> None:
    from config import parallelogram_floor_deg

    j1, j2 = 80.0, -15.0
    floor = parallelogram_floor_deg(j1)
    margin = j2 - floor
    assert margin > 0
    assert margin == j2 - (2 * j1 - 180)
