"""Typer CLI for the uArm Swift control suite.

When the FastAPI server is running on localhost:8000, motion commands are
forwarded to it so the arm state is shared with the 3D visualizer.
Otherwise falls back to a local SimulatedBus (Phase 2 behaviour).
"""

from __future__ import annotations

import code
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

import activities
import drawing
from arm import RECORDINGS_DIR, UArm
from config import DRAW_FEED_MM_S, TRAVEL_FEED_MM_S
from drawing import (
    grid_corners,
    load_drawing_config,
    save_drawing_config,
    unreachable_corners,
)
from kinematics import JointLimitError, WorkspaceError, in_workspace

app = typer.Typer(add_completion=False)

_SERVER_URL = "http://localhost:8000"


# ------------------------------------------------------------------
# Server helpers
# ------------------------------------------------------------------


def _server_running() -> bool:
    """Return True if the FastAPI server is reachable and responding."""
    try:
        with urllib.request.urlopen(f"{_SERVER_URL}/api/state", timeout=0.3) as resp:
            data = json.loads(resp.read())
            return "j0" in data and "x" in data
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return False


def _get_json(path: str) -> dict:
    """GET from the server and return the parsed JSON response."""
    with urllib.request.urlopen(f"{_SERVER_URL}{path}", timeout=30) as resp:
        return json.loads(resp.read())


def _post_json(path: str, data: dict) -> dict:
    """POST JSON to the server and return the parsed response."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{_SERVER_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        err = json.loads(exc.read())
        typer.echo(f"Error: {err.get('error', 'unknown error')}", err=True)
        raise typer.Exit(code=1) from None


def _handle_arm_error(exc: WorkspaceError | JointLimitError) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1)


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


@app.command()
def home() -> None:
    """Slow-home to a safe known pose."""
    if _server_running():
        data = _post_json("/api/home", {})
        typer.echo(f"Homed to ({data['x']:.1f}, {data['y']:.1f}, {data['z']:.1f})")
        typer.echo(
            f"Joints: j0={data['j0']:.2f} j1={data['j1']:.2f}"
            f" j2={data['j2']:.2f} j3={data['j3']:.2f}"
        )
        return
    with UArm() as arm:
        arm.home(blocking=True)
        pos = arm.get_position()
        a = arm.get_joint_angles()
        typer.echo(f"Homed to ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
        typer.echo(f"Joints: j0={a.j0:.2f} j1={a.j1:.2f} j2={a.j2:.2f} j3={a.j3:.2f}")


@app.command(context_settings={"ignore_unknown_options": True})
def goto(
    x: float,
    y: float,
    z: float,
    wrist: float = typer.Option(0.0, "--wrist", help="Wrist angle in degrees"),
    speed: float | None = typer.Option(None, "--speed", help="Max deg/s"),
) -> None:
    """Move the tool tip to a Cartesian position."""
    if _server_running():
        data = _post_json("/api/goto", {"x": x, "y": y, "z": z, "wrist": wrist, "speed": speed})
        typer.echo(f"Reached ({data['x']:.1f}, {data['y']:.1f}, {data['z']:.1f})")
        typer.echo(
            f"Joints: j0={data['j0']:.2f} j1={data['j1']:.2f}"
            f" j2={data['j2']:.2f} j3={data['j3']:.2f}"
        )
        return
    with UArm() as arm:
        try:
            arm.set_position(x, y, z, wrist=wrist, speed=speed, blocking=True)
        except (WorkspaceError, JointLimitError) as exc:
            _handle_arm_error(exc)
        pos = arm.get_position()
        a = arm.get_joint_angles()
        typer.echo(f"Reached ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
        typer.echo(f"Joints: j0={a.j0:.2f} j1={a.j1:.2f} j2={a.j2:.2f} j3={a.j3:.2f}")


@app.command(context_settings={"ignore_unknown_options": True})
def joints(
    j0: float,
    j1: float,
    j2: float,
    j3: float,
    speed: float | None = typer.Option(None, "--speed", help="Max deg/s"),
) -> None:
    """Move to a joint-space pose."""
    if _server_running():
        data = _post_json("/api/joints", {"j0": j0, "j1": j1, "j2": j2, "j3": j3, "speed": speed})
        typer.echo(
            f"Joints: j0={data['j0']:.2f} j1={data['j1']:.2f}"
            f" j2={data['j2']:.2f} j3={data['j3']:.2f}"
        )
        typer.echo(f"Position: ({data['x']:.1f}, {data['y']:.1f}, {data['z']:.1f})")
        return
    with UArm() as arm:
        try:
            arm.set_joint_angles(j0, j1, j2, j3, speed=speed, blocking=True)
        except (WorkspaceError, JointLimitError) as exc:
            _handle_arm_error(exc)
        pos = arm.get_position()
        a = arm.get_joint_angles()
        typer.echo(f"Joints: j0={a.j0:.2f} j1={a.j1:.2f} j2={a.j2:.2f} j3={a.j3:.2f}")
        typer.echo(f"Position: ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")


@app.command()
def where() -> None:
    """Print the current tool-tip position and joint angles."""
    if _server_running():
        data = _get_json("/api/state")
        typer.echo(f"Position: ({data['x']:.1f}, {data['y']:.1f}, {data['z']:.1f})")
        typer.echo(
            f"Joints: j0={data['j0']:.2f} j1={data['j1']:.2f}"
            f" j2={data['j2']:.2f} j3={data['j3']:.2f}"
        )
        return
    with UArm() as arm:
        pos = arm.get_position()
        a = arm.get_joint_angles()
        typer.echo(f"Position: ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
        typer.echo(f"Joints: j0={a.j0:.2f} j1={a.j1:.2f} j2={a.j2:.2f} j3={a.j3:.2f}")


# ------------------------------------------------------------------
# Recording / replay (always local — server recording is Phase 4+)
# ------------------------------------------------------------------


@app.command()
def record(name: str) -> None:
    """Record joint angles until Ctrl-C."""
    with UArm() as arm:
        arm.record_start(name)
        typer.echo(f"Recording '{name}'... press Ctrl-C to stop.")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            path = arm.record_stop()
            typer.echo(f"\nSaved to {path}")


@app.command()
def play(
    name: str,
    speed_factor: float = typer.Option(1.0, "--speed-factor", help="Playback speed multiplier"),
) -> None:
    """Replay a recording."""
    path = Path(name)
    if not path.suffix:
        path = RECORDINGS_DIR / f"{name}.json"
    if not path.exists():
        typer.echo(f"Error: recording not found: {path}", err=True)
        raise typer.Exit(code=1)
    with UArm() as arm:
        arm.replay(name, speed_factor=speed_factor, blocking=True)
        typer.echo("Replay complete.")


@app.command(name="list")
def list_recordings() -> None:
    """List saved recordings."""
    if not RECORDINGS_DIR.exists():
        typer.echo("No recordings directory yet.")
        return
    files = sorted(RECORDINGS_DIR.glob("*.json"))
    if not files:
        typer.echo("No recordings found.")
        return
    for f in files:
        typer.echo(f.stem)


# ------------------------------------------------------------------
# Activities
# ------------------------------------------------------------------

activity_app = typer.Typer(add_completion=False, help="Arm-driven activities (games, drawing).")
app.add_typer(activity_app, name="activity")


def _coerce(value: str) -> object:
    """Best-effort scalar coercion for `--option key=value` values."""
    for caster in (int, float):
        try:
            return caster(value)
        except ValueError:
            continue
    return value


def _print_board(board: list[list[str]]) -> None:
    sym = {"": " ", "X": "X", "O": "O"}
    rows = [" " + " | ".join(sym[board[r][c]] for c in range(3)) for r in range(3)]
    typer.echo(("\n" + "---+---+---\n").join(rows))


def _play_terminal_game(do_start, do_move) -> None:
    """Drive an interactive game in the terminal via the given callables."""
    state = do_start()
    typer.echo(f"\n{state['status']}")
    _print_board(state["board"])
    while not state["over"]:
        raw = typer.prompt("Your move 'row col' (0-2), or 'q' to quit")
        if raw.strip().lower() in ("q", "quit", "exit"):
            typer.echo("Quit.")
            return
        try:
            parts = raw.replace(",", " ").split()
            r, c = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            typer.echo("Enter two numbers 0-2, e.g. '1 2'.")
            continue
        if not (0 <= r <= 2 and 0 <= c <= 2) or state["board"][r][c]:
            typer.echo("That cell is taken or out of range.")
            continue
        typer.echo("Thinking…")
        state = do_move(r, c)
        typer.echo(f"\n{state['status']}")
        _print_board(state["board"])
    typer.echo(f"\nGame over: {state['status']}")


@activity_app.command("list")
def activity_list() -> None:
    """List available activities."""
    if _server_running():
        items = _get_json("/api/activities")["activities"]
    else:
        activities.discover()
        items = activities.list_activities()
    if not items:
        typer.echo("No activities found.")
        return
    for a in items:
        kind = "interactive" if a["interactive"] else "runnable"
        typer.echo(f"{a['slug']:14} [{kind:11}] {a['name']} — {a['description']}")


@activity_app.command("run")
def activity_run(
    slug: str,
    option: Annotated[
        list[str] | None,
        typer.Option("--option", "-o", help="Activity option as key=value (repeatable)."),
    ] = None,
) -> None:
    """Run an activity. Interactive activities (e.g. tic-tac-toe) play in the terminal."""
    options: dict[str, object] = {}
    for kv in option or []:
        key, _, val = kv.partition("=")
        options[key.strip()] = _coerce(val.strip())

    activities.discover()
    try:
        cls = activities.get_activity(slug)
    except KeyError:
        typer.echo(f"Error: unknown activity {slug!r}", err=True)
        raise typer.Exit(code=1) from None
    interactive = activities.is_interactive(cls)

    if _server_running():
        if interactive:
            _play_terminal_game(
                lambda: _post_json(f"/api/activities/{slug}/start", options),
                lambda r, c: _post_json(f"/api/activities/{slug}/move", {"row": r, "col": c}),
            )
        else:
            _post_json(f"/api/activities/{slug}/run", options)
            typer.echo(f"{slug} complete.")
        return

    # Local fallback — no shared 3D viz.
    arm = UArm().connect()
    arm.home(blocking=True)
    inst = cls()
    try:
        if interactive:
            _play_terminal_game(
                lambda: inst.start(arm, options),
                lambda r, c: inst.human_move(arm, row=r, col=c),
            )
        else:
            if options and hasattr(inst, "configure"):
                inst.configure(options)
            inst.setup(arm)
            try:
                inst.run(arm)
            finally:
                inst.cleanup(arm)
            typer.echo(f"{slug} complete.")
    except (WorkspaceError, JointLimitError) as exc:
        _handle_arm_error(exc)
    finally:
        arm.disconnect()


# ------------------------------------------------------------------
# Pen drawing calibration (Phase 8A)
# ------------------------------------------------------------------

pen_app = typer.Typer(
    add_completion=False,
    help="Pen drawing calibration: pen-down Z height and dry-run jog.",
)
app.add_typer(pen_app, name="pen")


@contextmanager
def _drawing_arm() -> Iterator[Callable[..., None]]:
    """Yield a ``goto(x, y, z, wrist)`` callable for pen jog/calibrate.

    Forwards to the running server (shared 3D viz) when one is up, otherwise
    drives a freshly slow-homed local UArm. Callers must only pass targets they
    have already checked with ``in_workspace`` / ``unreachable_corners``.
    """
    if _server_running():

        def goto(x: float, y: float, z: float, wrist: float = 0.0) -> None:
            _post_json("/api/goto", {"x": x, "y": y, "z": z, "wrist": wrist, "speed": None})

        yield goto
    else:
        with UArm() as arm:
            typer.echo("Slow-homing to a safe pose…")
            arm.home(blocking=True)

            def goto(x: float, y: float, z: float, wrist: float = 0.0) -> None:
                try:
                    arm.set_position(x, y, z, wrist=wrist, blocking=True)
                except (WorkspaceError, JointLimitError) as exc:
                    _handle_arm_error(exc)

            yield goto


@pen_app.command("show")
def pen_show() -> None:
    """Print the persisted pen-drawing config."""
    cfg = load_drawing_config()
    typer.echo(f"table_z  = {cfg.table_z:6.1f} mm   (pen-down contact height)")
    typer.echo(f"pen_up   = {cfg.pen_up:6.1f} mm   (travel clearance)")
    typer.echo(f"pen_up_z = {cfg.pen_up_z:6.1f} mm")
    typer.echo(f"wrist    = {cfg.wrist:6.1f} deg")
    feed = cfg.feed if cfg.feed is not None else DRAW_FEED_MM_S
    travel = cfg.travel_feed if cfg.travel_feed is not None else TRAVEL_FEED_MM_S
    feed_note = "" if cfg.feed is not None else "   (suite default — tune on paper)"
    travel_note = "" if cfg.travel_feed is not None else "   (suite default)"
    typer.echo(f"feed     = {feed:6.1f} mm/s (pen down){feed_note}")
    typer.echo(f"travel   = {travel:6.1f} mm/s (pen up){travel_note}")
    typer.echo(f"pen      = {cfg.pen_label or '(unlabeled)'}")
    path = drawing.DRAWING_PATH
    if path.exists():
        typer.echo(f"(saved at {path})")
    else:
        typer.echo(f"(no {path} yet — showing defaults)")


@pen_app.command("set")
def pen_set(
    table_z: float | None = typer.Option(None, "--table-z", help="Pen-down contact height (mm)"),
    pen_up: float | None = typer.Option(None, "--pen-up", help="Travel clearance above table (mm)"),
    wrist: float | None = typer.Option(None, "--wrist", help="Wrist angle while drawing (deg)"),
    feed: float | None = typer.Option(None, "--feed", help="Pen-down tool-tip speed (mm/s)"),
    travel_feed: float | None = typer.Option(
        None, "--travel-feed", help="Pen-up travel speed (mm/s)"
    ),
    label: str | None = typer.Option(None, "--label", help="Which pen this is calibrated for"),
) -> None:
    """Set one or more drawing-config values and save (no motion)."""
    cfg = load_drawing_config()
    if table_z is not None:
        cfg.table_z = table_z
    if pen_up is not None:
        cfg.pen_up = pen_up
    if wrist is not None:
        cfg.wrist = wrist
    if feed is not None:
        cfg.feed = feed
    if travel_feed is not None:
        cfg.travel_feed = travel_feed
    if label is not None:
        cfg.pen_label = label
    save_drawing_config(cfg)
    typer.echo(f"Saved to {drawing.DRAWING_PATH}.")
    pen_show()


@pen_app.command("calibrate")
def pen_calibrate(
    x: float = typer.Option(250.0, "--x", help="X to hover the pen over while jogging"),
    y: float = typer.Option(0.0, "--y", help="Y to hover the pen over while jogging"),
    start_z: float | None = typer.Option(None, "--start-z", help="Starting Z (default: pen_up_z)"),
    step: float = typer.Option(2.0, "--step", help="Initial jog step (mm)"),
) -> None:
    """Interactively jog Z down until the pen touches the paper, then save it.

    Moves the arm. Each step is workspace-checked before motion, so the pen is
    never commanded outside reach. Save records the current Z as ``table_z``.
    """
    cfg = load_drawing_config()
    z = start_z if start_z is not None else cfg.pen_up_z
    if not in_workspace(x, y, z, wrist=cfg.wrist):
        typer.echo(
            f"Error: start point ({x:.0f}, {y:.0f}, {z:.1f}) is outside the workspace.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo("Pen-down Z calibration.")
    typer.echo(f"Hovering the pen at ({x:.0f}, {y:.0f}); jog Z until it just kisses the paper.")
    typer.echo("Commands: [Enter] lower by step · 'u' raise by step · 'step <mm>' change step")
    typer.echo("          's' save table_z here · 'q' quit without saving")

    with _drawing_arm() as goto:
        goto(x, y, z, cfg.wrist)
        while True:
            raw = (
                typer.prompt(f"z={z:.1f}mm step={step:.1f}", default="", show_default=False)
                .strip()
                .lower()
            )
            if raw in ("q", "quit", "exit"):
                typer.echo("Aborted — nothing saved.")
                return
            if raw in ("s", "save"):
                cfg.table_z = z
                save_drawing_config(cfg)
                typer.echo(f"Saved table_z = {z:.1f} mm to {drawing.DRAWING_PATH}.")
                return
            if raw.startswith("step"):
                parts = raw.split()
                try:
                    step = abs(float(parts[1]))
                except (IndexError, ValueError):
                    typer.echo("Usage: step <mm>, e.g. 'step 0.5'")
                continue
            delta = step if raw in ("u", "up") else -step  # Enter (empty) = down
            new_z = z + delta
            if not in_workspace(x, y, new_z, wrist=cfg.wrist):
                typer.echo(f"  z={new_z:.1f} is outside the workspace — staying at {z:.1f}.")
                continue
            z = new_z
            goto(x, y, z, cfg.wrist)


@pen_app.command("jog-corners")
def pen_jog_corners(
    center_x: float = typer.Option(250.0, "--center-x", help="Grid center X (mm)"),
    center_y: float = typer.Option(0.0, "--center-y", help="Grid center Y (mm)"),
    cell: float = typer.Option(40.0, "--cell", help="Grid cell size (mm)"),
) -> None:
    """Dry-run: visit each grid corner at pen-up height to check placement.

    Validates every corner up front (refusing if any is unreachable) so the
    grid footprint is confirmed on paper before a single stroke is drawn.
    """
    cfg = load_drawing_config()
    corners = grid_corners(center_x, center_y, cell)
    bad = unreachable_corners(corners, cfg.pen_up_z, wrist=cfg.wrist)
    if bad:
        listed = ", ".join(f"({x:.0f}, {y:.0f})" for x, y in bad)
        typer.echo(
            f"Error: {len(bad)} grid corner(s) unreachable at pen-up Z "
            f"{cfg.pen_up_z:.1f}: {listed}. Move/shrink the grid.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Jogging the 4 grid corners at pen-up Z {cfg.pen_up_z:.1f} mm (pen never lowers).")
    with _drawing_arm() as goto:
        for i, (cx, cy) in enumerate(corners, start=1):
            typer.echo(f"  corner {i}/4 → ({cx:.0f}, {cy:.0f})")
            goto(cx, cy, cfg.pen_up_z, cfg.wrist)
            typer.prompt("    [Enter] for next corner", default="", show_default=False)
    typer.echo("Done — all four corners reached.")


@app.command()
def shell() -> None:
    """Open an interactive Python REPL with a connected UArm."""
    arm = UArm().connect()
    banner = (
        "uArm shell — `arm` is a connected UArm instance.\n"
        "Try: arm.get_position(), arm.home(), arm.set_position(250, 0, 50, blocking=True)\n"
        "Type exit() or Ctrl-D to quit."
    )
    try:
        code.interact(banner=banner, local={"arm": arm}, exitmsg="")
    finally:
        arm.disconnect()


if __name__ == "__main__":
    app()
