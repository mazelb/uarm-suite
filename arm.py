"""High-level UArm controller.

Wraps a ServoBus and exposes motion commands in the logical joint-angle /
Cartesian frames. Threading, recording, and replay live here. No hardware
imports — the bus abstraction handles the physical layer.
"""

from __future__ import annotations

import contextlib
import json
import math
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from config import (
    CHANNELS,
    DEFAULT_DEG_PER_SEC,
    DRAW_STEP_MM,
    SLOW_HOME_DEG_PER_SEC,
)
from hardware import ServoBus, make_bus
from kinematics import (
    JointAngles,
    Position,
    forward_kinematics,
    interpolate_line,
    inverse_kinematics,
)

HOME_JOINTS = JointAngles(j0=0.0, j1=45.0, j2=-45.0, j3=0.0)
RECORDING_HZ: float = 20.0
RECORDINGS_DIR = Path("recordings")

_JOINT_CHANNELS = (
    CHANNELS["J0"],
    CHANNELS["J1"],
    CHANNELS["J2"],
    CHANNELS["J3"],
)

_ARRIVAL_TOL_DEG: float = 0.5
_POLL_INTERVAL: float = 0.02


class UArm:
    """Main controller for one uArm Swift."""

    def __init__(self, bus: ServoBus | None = None) -> None:
        self._bus: ServoBus = bus or make_bus()
        self._target_joints: JointAngles | None = None
        self._position_callbacks: list[Callable[[Position], None]] = []
        self._connected = False

        self._moving = False
        self._move_thread: threading.Thread | None = None

        self._recording = False
        self._record_frames: list[dict[str, float]] = []
        self._record_start_t: float = 0.0
        self._record_name: str = ""
        self._record_thread: threading.Thread | None = None

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> UArm:
        self._bus.add_listener(self._on_bus_update)
        self._connected = True
        return self

    def disconnect(self) -> None:
        self._recording_stop_internal()
        self.wait_for_idle(timeout=5.0)
        self._connected = False
        self._bus.close()

    def __enter__(self) -> UArm:
        return self.connect()

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def home(self, blocking: bool = True) -> None:
        self._bus.set_speed(SLOW_HOME_DEG_PER_SEC)
        self._send_joints(HOME_JOINTS)
        if blocking:
            self.wait_for_idle()
        self._bus.set_speed(DEFAULT_DEG_PER_SEC)

    def set_joint_angles(
        self,
        j0: float,
        j1: float,
        j2: float,
        j3: float,
        *,
        speed: float | None = None,
        blocking: bool = False,
    ) -> None:
        angles = JointAngles(j0=j0, j1=j1, j2=j2, j3=j3)
        if speed is not None:
            self._bus.set_speed(speed)
        self._send_joints(angles)
        if blocking:
            self.wait_for_idle()
        if speed is not None:
            self._bus.set_speed(DEFAULT_DEG_PER_SEC)

    def set_position(
        self,
        x: float,
        y: float,
        z: float,
        *,
        wrist: float = 0.0,
        speed: float | None = None,
        blocking: bool = False,
    ) -> None:
        angles = inverse_kinematics(x, y, z, wrist=wrist)
        self.set_joint_angles(*angles, speed=speed, blocking=blocking)

    def get_joint_angles(self) -> JointAngles:
        return JointAngles(
            j0=self._bus.get_angle(_JOINT_CHANNELS[0]),
            j1=self._bus.get_angle(_JOINT_CHANNELS[1]),
            j2=self._bus.get_angle(_JOINT_CHANNELS[2]),
            j3=self._bus.get_angle(_JOINT_CHANNELS[3]),
        )

    def get_position(self) -> Position:
        a = self.get_joint_angles()
        return forward_kinematics(a.j0, a.j1, a.j2, a.j3)

    def move_linear(
        self,
        x: float,
        y: float,
        z: float,
        *,
        wrist: float = 0.0,
        feed: float,
        step_mm: float | None = None,
    ) -> None:
        """Move the tool tip in a straight line to (x, y, z) at ``feed`` mm/s.

        A plain joint-space slew between distant targets curves the tool path;
        this subdivides the segment into ``step_mm`` Cartesian steps and paces
        them so the *tip* moves at the requested feed (clamped where a step
        would exceed DEFAULT_DEG_PER_SEC on any joint). IK for every step is
        solved before any motion, so an unreachable midpoint refuses cleanly
        instead of half-drawing.

        Blocking by design: drawing code sequences strokes synchronously. Use
        ``set_position``/``move_along`` for fire-and-forget moves.
        """
        if feed <= 0:
            raise ValueError(f"feed must be positive mm/s, got {feed}")
        step = step_mm if step_mm is not None else DRAW_STEP_MM

        start_joints = self._target_joints
        if start_joints is None:
            start_joints = self.get_joint_angles()
        start = forward_kinematics(*start_joints)

        points = interpolate_line((start.x, start.y, start.z), (x, y, z), step)
        waypoints = [inverse_kinematics(px, py, pz, wrist=wrist) for px, py, pz in points]
        step_len = math.dist((start.x, start.y, start.z), (x, y, z)) / len(points)
        nominal_dt = step_len / feed

        prev = start_joints
        t_next = time.monotonic()
        try:
            for angles in waypoints:
                delta = max(abs(a - b) for a, b in zip(angles, prev, strict=True))
                prev = angles
                if delta < 1e-9:
                    continue
                dt = max(nominal_dt, delta / DEFAULT_DEG_PER_SEC)
                self._bus.set_speed(max(delta / dt, 1.0))
                self._send_joints(angles)
                t_next += dt
                pause = t_next - time.monotonic()
                if pause > 0:
                    time.sleep(pause)
            self._wait_at_target()
        finally:
            self._bus.set_speed(DEFAULT_DEG_PER_SEC)

    def move_along(
        self,
        path: Iterable[tuple[float, float, float]],
        *,
        wrist: float = 0.0,
        speed: float | None = None,
    ) -> None:
        waypoints = [inverse_kinematics(x, y, z, wrist=wrist) for x, y, z in path]
        if not waypoints:
            return

        if speed is not None:
            self._bus.set_speed(speed)

        with self._lock:
            self._moving = True

        def _run() -> None:
            try:
                for angles in waypoints:
                    self._send_joints(angles)
                    self._wait_at_target()
            finally:
                with self._lock:
                    self._moving = False
                if speed is not None:
                    self._bus.set_speed(DEFAULT_DEG_PER_SEC)

        self._move_thread = threading.Thread(target=_run, daemon=True)
        self._move_thread.start()

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            with self._lock:
                moving = self._moving
            if not moving and self._at_target():
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Position callbacks
    # ------------------------------------------------------------------

    def on_position(self, callback: Callable[[Position], None]) -> None:
        self._position_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Recording / replay
    # ------------------------------------------------------------------

    def record_start(self, name: str) -> None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._recording = True
            self._record_name = name
            self._record_frames = []
            self._record_start_t = time.monotonic()

        def _sample() -> None:
            dt = 1.0 / RECORDING_HZ
            while True:
                with self._lock:
                    if not self._recording:
                        break
                a = self.get_joint_angles()
                t = time.monotonic() - self._record_start_t
                self._record_frames.append(
                    {"t": round(t, 4), "j0": a.j0, "j1": a.j1, "j2": a.j2, "j3": a.j3}
                )
                time.sleep(dt)

        self._record_thread = threading.Thread(target=_sample, daemon=True)
        self._record_thread.start()

    def record_stop(self) -> Path:
        return self._recording_stop_internal()

    def _recording_stop_internal(self) -> Path:
        with self._lock:
            if not self._recording:
                return Path()
            self._recording = False
            name = self._record_name
            frames = list(self._record_frames)
        if self._record_thread is not None:
            self._record_thread.join(timeout=2.0)
            self._record_thread = None

        path = RECORDINGS_DIR / f"{name}.json"
        data = {"name": name, "frames": frames}
        path.write_text(json.dumps(data, indent=2))
        return path

    def replay(
        self,
        name_or_path: str | Path,
        *,
        speed_factor: float = 1.0,
        blocking: bool = True,
    ) -> None:
        path = Path(name_or_path)
        if not path.suffix:
            path = RECORDINGS_DIR / f"{path}.json"
        data = json.loads(path.read_text())
        frames: list[dict[str, float]] = data["frames"]
        if not frames:
            return

        first = frames[0]
        self.set_joint_angles(first["j0"], first["j1"], first["j2"], first["j3"], blocking=True)

        def _play() -> None:
            prev_t = first["t"]
            for frame in frames[1:]:
                dt = (frame["t"] - prev_t) / speed_factor
                if dt > 0:
                    time.sleep(dt)
                self._send_joints(
                    JointAngles(j0=frame["j0"], j1=frame["j1"], j2=frame["j2"], j3=frame["j3"])
                )
                prev_t = frame["t"]
            self._wait_at_target()
            with self._lock:
                self._moving = False

        with self._lock:
            self._moving = True

        t = threading.Thread(target=_play, daemon=True)
        t.start()
        if blocking:
            t.join()

    # ------------------------------------------------------------------
    # Actuator stubs
    # ------------------------------------------------------------------

    def set_pump(self, on: bool) -> None:
        self._bus.set_angle(CHANNELS["PUMP"], 90.0 if on else 0.0, immediate=True)

    def set_gripper(self, open_: bool) -> None:
        self._bus.set_angle(CHANNELS["GRIPPER"], 90.0 if open_ else 0.0, immediate=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send_joints(self, angles: JointAngles) -> None:
        self._target_joints = angles
        for i, ch in enumerate(_JOINT_CHANNELS):
            self._bus.set_angle(ch, angles[i])

    def _at_target(self) -> bool:
        if self._target_joints is None:
            return True
        a = self.get_joint_angles()
        return all(
            abs(getattr(a, f"j{i}") - self._target_joints[i]) < _ARRIVAL_TOL_DEG for i in range(4)
        )

    def _wait_at_target(self) -> None:
        while not self._at_target():
            time.sleep(_POLL_INTERVAL)

    def _on_bus_update(self, snapshot: dict[int, float]) -> None:
        j0 = snapshot.get(_JOINT_CHANNELS[0], 0.0)
        j1 = snapshot.get(_JOINT_CHANNELS[1], 0.0)
        j2 = snapshot.get(_JOINT_CHANNELS[2], 0.0)
        j3 = snapshot.get(_JOINT_CHANNELS[3], 0.0)
        pos = forward_kinematics(j0, j1, j2, j3)
        for cb in self._position_callbacks:
            with contextlib.suppress(Exception):
                cb(pos)
