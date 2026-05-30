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
from pathlib import Path
from typing import Annotated

import typer

import activities
from arm import RECORDINGS_DIR, UArm
from kinematics import JointLimitError, WorkspaceError

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
