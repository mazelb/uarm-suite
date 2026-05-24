"""FastAPI server for the uArm Swift control suite.

Holds a persistent UArm instance. REST endpoints wrap UArm methods; a
WebSocket streams joint state at ~50 Hz for the 3D visualization.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from arm import UArm
from config import SIM_UPDATE_HZ
from kinematics import JointLimitError, WorkspaceError

_arm: UArm | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _arm
    if _arm is None:
        _arm = UArm()
        _arm.connect()
        await asyncio.to_thread(_arm.home, True)
    yield
    if _arm is not None:
        _arm.disconnect()
        _arm = None


app = FastAPI(lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class GotoCommand(BaseModel):
    x: float
    y: float
    z: float
    wrist: float = 0.0
    speed: float | None = None


class JointsCommand(BaseModel):
    j0: float
    j1: float
    j2: float
    j3: float
    speed: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_dict() -> dict[str, float]:
    assert _arm is not None
    angles = _arm.get_joint_angles()
    pos = _arm.get_position()
    return {
        "j0": round(angles.j0, 2),
        "j1": round(angles.j1, 2),
        "j2": round(angles.j2, 2),
        "j3": round(angles.j3, 2),
        "x": round(pos.x, 1),
        "y": round(pos.y, 1),
        "z": round(pos.z, 1),
    }


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/state")
async def api_state() -> dict[str, float]:
    return _state_dict()


@app.get("/api/where")
async def api_where() -> dict[str, float]:
    return _state_dict()


@app.post("/api/home")
async def api_home() -> dict[str, float]:
    assert _arm is not None
    await asyncio.to_thread(_arm.home, True)
    return _state_dict()


@app.post("/api/goto")
async def api_goto(cmd: GotoCommand):
    assert _arm is not None
    try:
        await asyncio.to_thread(
            _arm.set_position,
            cmd.x,
            cmd.y,
            cmd.z,
            wrist=cmd.wrist,
            speed=cmd.speed,
            blocking=True,
        )
    except (WorkspaceError, JointLimitError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    return _state_dict()


@app.post("/api/joints")
async def api_joints(cmd: JointsCommand):
    assert _arm is not None
    try:
        await asyncio.to_thread(
            _arm.set_joint_angles,
            cmd.j0,
            cmd.j1,
            cmd.j2,
            cmd.j3,
            speed=cmd.speed,
            blocking=True,
        )
    except (WorkspaceError, JointLimitError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    return _state_dict()


# ---------------------------------------------------------------------------
# WebSocket — streams joint state at ~50 Hz
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    dt = 1.0 / SIM_UPDATE_HZ
    try:
        while True:
            await websocket.send_json(_state_dict())
            await asyncio.sleep(dt)
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Static files (index.html, viz.js, style.css)
# ---------------------------------------------------------------------------

if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
