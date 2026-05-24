"""Tests for server.py — FastAPI REST endpoints and WebSocket."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from arm import UArm
from hardware import SimulatedBus


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 10000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 10000.0)

    import server

    bus = SimulatedBus(max_deg_per_sec=10000)
    arm = UArm(bus=bus)
    arm.connect()
    arm.home(blocking=True)
    server._arm = arm
    with TestClient(server.app) as c:
        yield c


# ------------------------------------------------------------------
# GET /api/state
# ------------------------------------------------------------------


def test_state_returns_expected_keys(client: TestClient) -> None:
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("j0", "j1", "j2", "j3", "x", "y", "z"):
        assert key in data


# ------------------------------------------------------------------
# GET /api/where (alias)
# ------------------------------------------------------------------


def test_where_is_state_alias(client: TestClient) -> None:
    resp = client.get("/api/where")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("j0", "j1", "j2", "j3", "x", "y", "z"):
        assert key in data


# ------------------------------------------------------------------
# POST /api/home
# ------------------------------------------------------------------


def test_home_returns_home_pose(client: TestClient) -> None:
    resp = client.post("/api/home")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["j1"] - 45.0) < 1.0
    assert abs(data["j2"] - (-45.0)) < 1.0


# ------------------------------------------------------------------
# POST /api/goto
# ------------------------------------------------------------------


def test_goto_success(client: TestClient) -> None:
    resp = client.post("/api/goto", json={"x": 250, "y": 0, "z": 50})
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["x"] - 250.0) < 2.0
    assert abs(data["z"] - 50.0) < 2.0


def test_goto_workspace_error(client: TestClient) -> None:
    resp = client.post("/api/goto", json={"x": 500, "y": 0, "z": 80})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "max reach" in data["error"]


def test_goto_joint_limit_error(client: TestClient) -> None:
    resp = client.post("/api/goto", json={"x": 200, "y": 0, "z": 80})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "parallelogram" in data["error"]


# ------------------------------------------------------------------
# POST /api/joints
# ------------------------------------------------------------------


def test_joints_success(client: TestClient) -> None:
    resp = client.post("/api/joints", json={"j0": 0, "j1": 60, "j2": -30, "j3": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["j1"] - 60.0) < 1.0
    assert abs(data["j2"] - (-30.0)) < 1.0


# ------------------------------------------------------------------
# WebSocket /ws
# ------------------------------------------------------------------


def test_websocket_streams_state(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        for key in ("j0", "j1", "j2", "j3", "x", "y", "z"):
            assert key in data
