"""Servo bus abstraction layer.

Defines the ServoBus protocol and two implementations:
- SimulatedBus: software-only, slews angles at configurable speed
- PCA9685Bus: real hardware via Adafruit PCA9685 (lazy imports)

All angles passed through the bus are in the logical joint-angle frame.
PCA9685Bus applies SERVO_CALIBRATION internally when writing PWM.
"""

from __future__ import annotations

import contextlib
import os
import random
import threading
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from config import (
    DEFAULT_DEG_PER_SEC,
    I2C_ADDRESS,
    PWM_FREQUENCY_HZ,
    SERVO_CALIBRATION,
    SIM_UPDATE_HZ,
)


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


def joint_to_servo(channel: int, joint_deg: float) -> float:
    """Convert a joint-frame angle to a servo-frame angle via SERVO_CALIBRATION."""
    cal = SERVO_CALIBRATION.get(channel)
    if cal is None:
        return joint_deg
    return cal["zero_deg"] + cal["direction"] * joint_deg


def servo_to_joint(channel: int, servo_deg: float) -> float:
    """Convert a servo-frame angle back to a joint-frame angle."""
    cal = SERVO_CALIBRATION.get(channel)
    if cal is None:
        return servo_deg
    return cal["direction"] * (servo_deg - cal["zero_deg"])


class PCA9685Bus:
    """Real hardware bus via Adafruit PCA9685.

    Lazy-imports board/busio/adafruit_pca9685 in __init__. Tracks and slews
    joint-frame angles internally; converts to servo angles and writes PWM
    duty cycles on each tick of the background thread.
    """

    def __init__(
        self,
        *,
        max_deg_per_sec: float = DEFAULT_DEG_PER_SEC,
        i2c_address: int = I2C_ADDRESS,
        pwm_frequency: int = PWM_FREQUENCY_HZ,
    ) -> None:
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685
        except ImportError as exc:
            raise RuntimeError(
                "PCA9685Bus requires adafruit-circuitpython-pca9685, board, "
                "and busio. Install them on the Raspberry Pi."
            ) from exc

        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(self._i2c, address=i2c_address)
        self._pca.frequency = pwm_frequency
        self._pwm_period_us = 1_000_000.0 / pwm_frequency

        self._max_dps = max_deg_per_sec
        self._lock = threading.Lock()
        self._current: dict[int, float] = {}
        self._targets: dict[int, float] = {}
        self._listeners: list[Callable[[dict[int, float]], None]] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def _write_pwm(self, channel: int, joint_deg: float) -> None:
        servo_deg = joint_to_servo(channel, joint_deg)
        servo_deg = max(0.0, min(180.0, servo_deg))
        cal = SERVO_CALIBRATION.get(channel, {"min_us": 500, "max_us": 2500})
        min_us = cal["min_us"]
        max_us = cal["max_us"]
        pulse_us = min_us + (servo_deg / 180.0) * (max_us - min_us)
        duty_cycle = int(pulse_us / self._pwm_period_us * 65535)
        self._pca.channels[channel].duty_cycle = max(0, min(65535, duty_cycle))

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
                self._write_pwm(channel, degrees)
            self._targets[channel] = degrees

    def get_angle(self, channel: int) -> float:
        with self._lock:
            return self._current.get(channel, 0.0)

    def disable(self, channel: int) -> None:
        with self._lock:
            self._targets.pop(channel, None)
            self._pca.channels[channel].duty_cycle = 0

    def add_listener(self, callback: Callable[[dict[int, float]], None]) -> None:
        self._listeners.append(callback)

    def set_speed(self, deg_per_sec: float) -> None:
        self._max_dps = deg_per_sec

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for ch in list(self._current):
            with contextlib.suppress(Exception):
                self._pca.channels[ch].duty_cycle = 0
        with contextlib.suppress(Exception):
            self._pca.deinit()
        with contextlib.suppress(Exception):
            self._i2c.deinit()

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
                    self._current[ch] = new
                    self._write_pwm(ch, new)
                snapshot = dict(self._current)
            for cb in self._listeners:
                with contextlib.suppress(Exception):
                    cb(snapshot)
            time.sleep(dt)


def make_bus(mode: str | None = None) -> ServoBus:
    """Create a ServoBus based on UARM_MODE env var (default ``sim``).

    Modes:
      ``sim``       — SimulatedBus (default; fakes arm physics).
      ``hardware``  — real PCA9685Bus driving servos via I2C (needs a Pi).
      ``mock``      — real PCA9685Bus against a fake PCA9685 (no Pi). Exercises
                      the genuine hardware code path on a dev machine; set
                      ``UARM_MOCK_VERBOSE=1`` to print each servo write.
    """
    if mode is None:
        mode = os.environ.get("UARM_MODE", "sim")
    if mode == "sim":
        return SimulatedBus()
    if mode == "hardware":
        return PCA9685Bus()
    if mode == "mock":
        import mockhw

        verbose = os.environ.get("UARM_MOCK_VERBOSE", "").lower() in ("1", "true", "yes")
        mockhw.install(verbose=verbose)
        return PCA9685Bus()
    raise ValueError(f"unknown UARM_MODE: {mode!r} (expected 'sim', 'hardware', or 'mock')")
