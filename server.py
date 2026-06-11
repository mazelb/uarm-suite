"""FastAPI server for the uArm Swift control suite.

Holds a persistent UArm instance. REST endpoints wrap UArm methods; a
WebSocket streams joint state at ~50 Hz for the 3D visualization.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import activities
import drawing
from arm import RECORDINGS_DIR, UArm
from config import (
    DRAW_FEED_MM_S,
    SERVO_CALIBRATION,
    SIM_UPDATE_HZ,
    TRAVEL_FEED_MM_S,
    ServoCalibration,
)
from drawing import (
    grid_corners,
    load_drawing_config,
    save_drawing_config,
    unreachable_corners,
)
from kinematics import (
    JointAngles,
    JointLimitError,
    WorkspaceError,
    check_joint_limits,
)

_arm: UArm | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"
CALIBRATION_PATH = Path("calibration.json")

# One interactive activity session at a time, guarded so overlapping move
# requests can't interleave arm commands.
_session: object | None = None
_session_slug: str | None = None
_session_lock = threading.Lock()


def _load_calibration() -> None:
    """Load calibration.json (if it exists) into SERVO_CALIBRATION in place."""
    if not CALIBRATION_PATH.exists():
        return
    data = json.loads(CALIBRATION_PATH.read_text())
    for ch_str, cal in data.items():
        ch = int(ch_str)
        if ch in SERVO_CALIBRATION:
            SERVO_CALIBRATION[ch].update(cal)


def _save_calibration() -> None:
    """Persist SERVO_CALIBRATION to calibration.json."""
    data = {str(ch): dict(cal) for ch, cal in SERVO_CALIBRATION.items()}
    CALIBRATION_PATH.write_text(json.dumps(data, indent=2))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _arm
    _load_calibration()
    activities.discover()
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


class RecordStartCommand(BaseModel):
    name: str


class PlayCommand(BaseModel):
    name: str
    speed_factor: float = 1.0


class CalibrationUpdate(BaseModel):
    channel: int
    min_us: int | None = None
    max_us: int | None = None
    zero_deg: float | None = None
    direction: int | None = None


class PenUpdate(BaseModel):
    # All fields optional; only the ones present in the request are applied.
    # An explicit null feed/travel_feed clears the override back to the suite
    # default (distinguished from "absent" via model_fields_set).
    table_z: float | None = None
    pen_up: float | None = None
    wrist: float | None = None
    feed: float | None = None
    travel_feed: float | None = None
    pen_label: str | None = None


class PenJogCommand(BaseModel):
    center_x: float = 250.0
    center_y: float = 0.0
    cell: float = 40.0


class ActivityStart(BaseModel):
    # Opaque per-activity options (e.g. tic-tac-toe grid placement). Extra keys
    # are accepted and passed straight through to the activity.
    model_config = {"extra": "allow"}


class ActivityMove(BaseModel):
    # Opaque per-activity action (e.g. {"row": 1, "col": 2}).
    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_dict() -> dict:
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
        "recording": _arm._recording,
    }


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/state")
async def api_state() -> dict:
    return _state_dict()


@app.get("/api/where")
async def api_where() -> dict:
    return _state_dict()


@app.post("/api/home")
async def api_home() -> dict:
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
        check_joint_limits(JointAngles(j0=cmd.j0, j1=cmd.j1, j2=cmd.j2, j3=cmd.j3))
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
# Recording / replay endpoints
# ---------------------------------------------------------------------------


@app.post("/api/record/start")
async def api_record_start(cmd: RecordStartCommand):
    assert _arm is not None
    _arm.record_start(cmd.name)
    return {"status": "recording", "name": cmd.name}


@app.post("/api/record/stop")
async def api_record_stop():
    assert _arm is not None
    path = await asyncio.to_thread(_arm.record_stop)
    return {"status": "stopped", "path": str(path)}


@app.get("/api/recordings")
async def api_recordings():
    if not RECORDINGS_DIR.is_dir():
        return {"recordings": []}
    names = sorted(p.stem for p in RECORDINGS_DIR.glob("*.json"))
    return {"recordings": names}


@app.post("/api/play")
async def api_play(cmd: PlayCommand):
    assert _arm is not None
    try:
        await asyncio.to_thread(
            _arm.replay,
            cmd.name,
            speed_factor=cmd.speed_factor,
            blocking=True,
        )
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": f"Recording '{cmd.name}' not found"})
    return _state_dict()


# ---------------------------------------------------------------------------
# Calibration endpoints
# ---------------------------------------------------------------------------


@app.get("/api/calibration")
async def api_calibration() -> dict:
    return {str(ch): dict(cal) for ch, cal in SERVO_CALIBRATION.items()}


@app.post("/api/calibration")
async def api_calibration_update(cmd: CalibrationUpdate):
    if cmd.channel not in SERVO_CALIBRATION:
        return JSONResponse(status_code=422, content={"error": f"Unknown channel {cmd.channel}"})
    cal: ServoCalibration = SERVO_CALIBRATION[cmd.channel]
    if cmd.min_us is not None:
        cal["min_us"] = cmd.min_us
    if cmd.max_us is not None:
        cal["max_us"] = cmd.max_us
    if cmd.zero_deg is not None:
        cal["zero_deg"] = cmd.zero_deg
    if cmd.direction is not None:
        if cmd.direction not in (1, -1):
            return JSONResponse(status_code=422, content={"error": "direction must be +1 or -1"})
        cal["direction"] = cmd.direction
    return {str(ch): dict(c) for ch, c in SERVO_CALIBRATION.items()}


@app.post("/api/calibration/save")
async def api_calibration_save():
    _save_calibration()
    return {"status": "saved", "path": str(CALIBRATION_PATH)}


@app.post("/api/calibration/reset")
async def api_calibration_reset():
    for ch in SERVO_CALIBRATION:
        SERVO_CALIBRATION[ch] = ServoCalibration(
            min_us=500,
            max_us=2500,
            zero_deg=90.0,
            direction=1,
        )
    return {str(ch): dict(cal) for ch, cal in SERVO_CALIBRATION.items()}


# ---------------------------------------------------------------------------
# Pen / drawing config (drawing.json)
# ---------------------------------------------------------------------------


def _pen_dict() -> dict:
    cfg = load_drawing_config()
    return {
        "table_z": cfg.table_z,
        "pen_up": cfg.pen_up,
        "pen_up_z": cfg.pen_up_z,
        "wrist": cfg.wrist,
        "pen_label": cfg.pen_label,
        "feed": cfg.feed,
        "travel_feed": cfg.travel_feed,
        "effective_feed": cfg.feed if cfg.feed is not None else DRAW_FEED_MM_S,
        "effective_travel_feed": (
            cfg.travel_feed if cfg.travel_feed is not None else TRAVEL_FEED_MM_S
        ),
        "saved": drawing.DRAWING_PATH.exists(),
    }


@app.get("/api/pen")
async def api_pen() -> dict:
    return _pen_dict()


@app.post("/api/pen")
async def api_pen_update(cmd: PenUpdate) -> dict:
    cfg = load_drawing_config()
    for field in cmd.model_fields_set:
        value = getattr(cmd, field)
        if value is None and field not in ("feed", "travel_feed", "pen_label"):
            continue  # null only clears the clearable fields
        setattr(cfg, field, value)
    if cfg.pen_label is None:  # null label = clear it
        cfg.pen_label = ""
    save_drawing_config(cfg)
    return _pen_dict()


@app.post("/api/pen/jog-corners")
async def api_pen_jog_corners(cmd: PenJogCommand):
    """Dry-run: visit the four grid corners at pen-up height.

    All corners are validated up front (422 if any is unreachable). The first
    corner is approached with a joint-space move; corner-to-corner edges run
    straight at the travel feed, each refusing before motion if a midpoint is
    out of reach.
    """
    assert _arm is not None
    cfg = load_drawing_config()
    corners = grid_corners(cmd.center_x, cmd.center_y, cmd.cell)
    bad = unreachable_corners(corners, cfg.pen_up_z, wrist=cfg.wrist)
    if bad:
        listed = ", ".join(f"({x:.0f}, {y:.0f})" for x, y in bad)
        return JSONResponse(
            status_code=422,
            content={
                "error": (
                    f"{len(bad)} grid corner(s) unreachable at pen-up Z "
                    f"{cfg.pen_up_z:.1f}: {listed}. Move/shrink the grid."
                )
            },
        )
    travel = cfg.travel_feed if cfg.travel_feed is not None else TRAVEL_FEED_MM_S

    def _jog() -> None:
        x0, y0 = corners[0]
        _arm.set_position(x0, y0, cfg.pen_up_z, wrist=cfg.wrist, blocking=True)
        for x, y in [*corners[1:], corners[0]]:  # loop back to close the rectangle
            _arm.move_linear(x, y, cfg.pen_up_z, wrist=cfg.wrist, feed=travel)

    try:
        await asyncio.to_thread(_jog)
    except (WorkspaceError, JointLimitError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    return {"status": "done", "corners": corners, "pen_up_z": cfg.pen_up_z}


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


@app.get("/api/activities")
async def api_activities() -> dict:
    return {"activities": activities.list_activities()}


@app.post("/api/activities/{slug}/run")
async def api_activity_run(slug: str, cmd: ActivityStart):
    assert _arm is not None
    try:
        cls = activities.get_activity(slug)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": f"unknown activity {slug!r}"})
    options = cmd.model_dump()

    def _run() -> None:
        inst = cls()
        # Optional per-activity configuration from the request body.
        if options and hasattr(inst, "configure"):
            inst.configure(options)
        with _session_lock:
            inst.setup(_arm)
            try:
                inst.run(_arm)
            finally:
                inst.cleanup(_arm)

    try:
        await asyncio.to_thread(_run)
    except (WorkspaceError, JointLimitError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    return {"status": "done", "slug": slug}


@app.post("/api/activities/{slug}/start")
async def api_activity_start(slug: str, cmd: ActivityStart):
    global _session, _session_slug
    assert _arm is not None
    try:
        cls = activities.get_activity(slug)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": f"unknown activity {slug!r}"})
    if not activities.is_interactive(cls):
        return JSONResponse(
            status_code=422, content={"error": f"{slug!r} is not an interactive activity"}
        )

    inst = cls()
    options = cmd.model_dump()

    def _start() -> dict:
        with _session_lock:
            return inst.start(_arm, options)

    try:
        state = await asyncio.to_thread(_start)
    except (WorkspaceError, JointLimitError, ValueError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    _session, _session_slug = inst, slug
    return state


@app.post("/api/activities/{slug}/move")
async def api_activity_move(slug: str, cmd: ActivityMove):
    assert _arm is not None
    if _session is None or _session_slug != slug:
        return JSONResponse(status_code=409, content={"error": f"no active {slug!r} session"})
    action = cmd.model_dump()
    session = _session

    def _move() -> dict:
        with _session_lock:
            return session.human_move(_arm, **action)

    try:
        return await asyncio.to_thread(_move)
    except (WorkspaceError, JointLimitError, ValueError, TypeError) as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})


@app.get("/api/activities/{slug}/state")
async def api_activity_state(slug: str):
    if _session is None or _session_slug != slug:
        return JSONResponse(status_code=409, content={"error": f"no active {slug!r} session"})
    return _session.state()


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
