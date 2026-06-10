"""Tests for server.py — FastAPI REST endpoints and WebSocket."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from arm import UArm
from hardware import SimulatedBus


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 10000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 10000.0)
    monkeypatch.setattr("activities._draw.DRAW_FEED_MM_S", 1e6)
    monkeypatch.setattr("activities._draw.TRAVEL_FEED_MM_S", 1e6)
    monkeypatch.setattr("arm.RECORDINGS_DIR", tmp_path / "recordings")

    import server

    monkeypatch.setattr(server, "RECORDINGS_DIR", tmp_path / "recordings")

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
    for key in ("j0", "j1", "j2", "j3", "x", "y", "z", "recording"):
        assert key in data
    assert data["recording"] is False


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


def test_joints_limit_error(client: TestClient) -> None:
    resp = client.post("/api/joints", json={"j0": 0, "j1": 80, "j2": -30, "j3": 0})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "parallelogram" in data["error"]


# ------------------------------------------------------------------
# WebSocket /ws
# ------------------------------------------------------------------


def test_websocket_streams_state(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        for key in ("j0", "j1", "j2", "j3", "x", "y", "z", "recording"):
            assert key in data


# ------------------------------------------------------------------
# Recording / replay
# ------------------------------------------------------------------


def test_record_start_stop(client: TestClient) -> None:
    resp = client.post("/api/record/start", json={"name": "test_rec"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "recording"

    state = client.get("/api/state").json()
    assert state["recording"] is True

    resp = client.post("/api/record/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_recordings_list(client: TestClient) -> None:
    resp = client.get("/api/recordings")
    assert resp.status_code == 200
    assert resp.json()["recordings"] == []

    client.post("/api/record/start", json={"name": "alpha"})
    client.post("/api/record/stop")

    resp = client.get("/api/recordings")
    assert "alpha" in resp.json()["recordings"]


def test_replay(client: TestClient) -> None:
    client.post("/api/record/start", json={"name": "replay_test"})
    client.post("/api/joints", json={"j0": 10, "j1": 60, "j2": -30, "j3": 0})
    client.post("/api/record/stop")

    resp = client.post("/api/play", json={"name": "replay_test"})
    assert resp.status_code == 200


def test_replay_not_found(client: TestClient) -> None:
    resp = client.post("/api/play", json={"name": "nonexistent"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"]


# ------------------------------------------------------------------
# Activities
# ------------------------------------------------------------------


def test_activities_list(client: TestClient) -> None:
    resp = client.get("/api/activities")
    assert resp.status_code == 200
    slugs = {a["slug"]: a for a in resp.json()["activities"]}
    assert "tic-tac-toe" in slugs
    assert slugs["tic-tac-toe"]["interactive"] is True


def test_tic_tac_toe_start_and_move(client: TestClient) -> None:
    resp = client.post("/api/activities/tic-tac-toe/start", json={})
    assert resp.status_code == 200
    state = resp.json()
    assert state["started"] is True
    assert state["turn"] == "X"

    resp = client.post("/api/activities/tic-tac-toe/move", json={"row": 1, "col": 1})
    assert resp.status_code == 200
    state = resp.json()
    assert state["board"][1][1] == "X"

    # state endpoint mirrors the session
    resp = client.get("/api/activities/tic-tac-toe/state")
    assert resp.status_code == 200
    assert resp.json()["board"][1][1] == "X"


def test_tic_tac_toe_invalid_move_422(client: TestClient) -> None:
    client.post("/api/activities/tic-tac-toe/start", json={})
    client.post("/api/activities/tic-tac-toe/move", json={"row": 0, "col": 0})
    resp = client.post("/api/activities/tic-tac-toe/move", json={"row": 0, "col": 0})
    assert resp.status_code == 422


def test_move_without_session_409(client: TestClient) -> None:
    server_mod = __import__("server")
    server_mod._session = None
    server_mod._session_slug = None
    resp = client.post("/api/activities/tic-tac-toe/move", json={"row": 0, "col": 0})
    assert resp.status_code == 409


def test_unknown_activity_404(client: TestClient) -> None:
    resp = client.post("/api/activities/nope/start", json={})
    assert resp.status_code == 404
