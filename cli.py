"""Typer CLI for the uArm Swift control suite."""

from __future__ import annotations

import code
import time
from pathlib import Path

import typer

from arm import RECORDINGS_DIR, UArm
from kinematics import JointLimitError, WorkspaceError

app = typer.Typer(add_completion=False)


def _handle_arm_error(exc: WorkspaceError | JointLimitError) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1)


@app.command()
def home() -> None:
    """Slow-home to a safe known pose."""
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
    with UArm() as arm:
        pos = arm.get_position()
        a = arm.get_joint_angles()
        typer.echo(f"Position: ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
        typer.echo(f"Joints: j0={a.j0:.2f} j1={a.j1:.2f} j2={a.j2:.2f} j3={a.j3:.2f}")


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
