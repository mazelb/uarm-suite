"""Servo bus abstraction layer.

Defines the ServoBus protocol and two implementations:
- SimulatedBus: software-only, slews angles at configurable speed
- PCA9685Bus: stub for real hardware (lazy imports, Phase 5)

All angles passed through the bus are in the logical joint-angle frame.
PCA9685Bus will apply SERVO_CALIBRATION internally (Phase 5).
"""

from __future__ import annotations

import contextlib
import os
import random
import threading
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from config import DEFAULT_DEG_PER_SEC, SIM_UPDATE_HZ


@runtime_checkable
class ServoBus(Protocol):
    """Minimal contract every servo bus must satisfy."""

    def set_angle(self, channel: int, degrees: float, *, immediate: bool = False) -> None: ...
    def get_angle(self, channel: int) -> float: ...
    def disable(self, channel: int) -> None: ...
    def add_listener(self, callback: Callable[[dict[int, float]], None]) -> None: ...
    def set_speed(self, deg_per_sec: float) -> None: ...
    def close(self) -> None: ...


class SimulatedBus:
    """Software servo bus that slews toward target angles at a configurable rate."""

    def __init__(
        self,
        *,
        max_deg_per_sec: float = DEFAULT_DEG_PER_SEC,
        jitter: bool = False,
    ) -> None:
        self._max_dps = max_deg_per_sec
        self._jitter = jitter
        self._lock = threading.Lock()
        self._current: dict[int, float] = {}
        self._targets: dict[int, float] = {}
        self._listeners: list[Callable[[dict[int, float]], None]] = []
        self._commands: list[dict[str, object]] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def _ensure_running(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def set_angle(self, channel: int, degrees: float, *, immediate: bool = False) -> None:
        self._ensure_running()
        with self._lock:
            if channel not in self._current:
                self._current[channel] = 0.0
            if immediate:
                self._current[channel] = degrees
            self._targets[channel] = degrees
            self._commands.append(
                {
                    "t": time.monotonic(),
                    "channel": channel,
                    "degrees": degrees,
                    "immediate": immediate,
                }
            )

    def get_angle(self, channel: int) -> float:
        with self._lock:
            return self._current.get(channel, 0.0)

    def disable(self, channel: int) -> None:
        with self._lock:
            self._targets.pop(channel, None)

    def add_listener(self, callback: Callable[[dict[int, float]], None]) -> None:
        self._listeners.append(callback)

    def set_speed(self, deg_per_sec: float) -> None:
        self._max_dps = deg_per_sec

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def commands(self) -> list[dict[str, object]]:
        return list(self._commands)

    def is_idle(self) -> bool:
        with self._lock:
            for ch, target in self._targets.items():
                current = self._current.get(ch, 0.0)
                if abs(current - target) > 0.6:
                    return False
            return True

    def _tick_loop(self) -> None:
        dt = 1.0 / SIM_UPDATE_HZ
        while self._running:
            with self._lock:
                for ch in list(self._targets):
                    target = self._targets[ch]
                    current = self._current.get(ch, 0.0)
                    diff = target - current
                    max_step = self._max_dps * dt
                    if abs(diff) <= max_step:
                        new = target
                    else:
                        new = current + max_step * (1.0 if diff > 0 else -1.0)
                    if self._jitter and abs(diff) > max_step:
                        new += random.uniform(-0.5, 0.5)
                    self._current[ch] = new
                snapshot = dict(self._current)
            for cb in self._listeners:
                with contextlib.suppress(Exception):
                    cb(snapshot)
            time.sleep(dt)


class PCA9685Bus:
    """Real hardware bus via Adafruit PCA9685 — stub for Phase 5."""

    def __init__(self) -> None:
        try:
            import board  # noqa: F401
            import busio  # noqa: F401
            from adafruit_pca9685 import PCA9685  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "PCA9685Bus requires adafruit-circuitpython-pca9685, board, "
                "and busio. Install them on the Raspberry Pi."
            ) from exc
        raise NotImplementedError("PCA9685Bus is a Phase 5 stub — do not instantiate yet")

    def set_angle(self, channel: int, degrees: float, *, immediate: bool = False) -> None:
        raise NotImplementedError

    def get_angle(self, channel: int) -> float:
        raise NotImplementedError

    def disable(self, channel: int) -> None:
        raise NotImplementedError

    def add_listener(self, callback: Callable[[dict[int, float]], None]) -> None:
        raise NotImplementedError

    def set_speed(self, deg_per_sec: float) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def make_bus(mode: str | None = None) -> ServoBus:
    """Create a ServoBus based on UARM_MODE env var (default ``sim``)."""
    if mode is None:
        mode = os.environ.get("UARM_MODE", "sim")
    if mode == "sim":
        return SimulatedBus()
    if mode == "hardware":
        return PCA9685Bus()
    raise ValueError(f"unknown UARM_MODE: {mode!r} (expected 'sim' or 'hardware')")
