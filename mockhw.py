"""Fake Adafruit/board/busio stack for running the REAL hardware code path
without a Raspberry Pi.

Calling :func:`install` injects stand-in ``board``, ``busio`` and
``adafruit_pca9685`` modules into ``sys.modules``. After that, constructing a
real :class:`hardware.PCA9685Bus` succeeds on a dev machine and exercises the
genuine code — PWM duty-cycle math, the 50 Hz slew loop, calibration
conversion, per-channel writes — against an in-memory fake PCA9685 instead of
silicon. Selected via ``UARM_MODE=mock`` (see :func:`hardware.make_bus`).

This is a *dry run*, not a simulation of arm physics: it shows exactly what
pulse widths the driver would send to each servo. Set ``UARM_MOCK_VERBOSE=1``
to print every channel write (noisy at 50 Hz — handy for a single move, not a
whole game).

Kept out of the production import path: nothing imports this module unless mock
mode is explicitly requested, so the lazy-import rule (CLAUDE.md rule 1) holds.
"""

from __future__ import annotations

import sys
import types

_VERBOSE = False


class _FakeChannel:
    """One PCA9685 output channel. Writing ``duty_cycle`` records the value."""

    def __init__(self, index: int, owner: FakePCA9685) -> None:
        self._index = index
        self._owner = owner
        self._duty = 0

    @property
    def duty_cycle(self) -> int:
        return self._duty

    @duty_cycle.setter
    def duty_cycle(self, value: int) -> None:
        self._duty = value
        self._owner._on_write(self._index, value)


class _FakeChannels:
    def __init__(self, owner: FakePCA9685) -> None:
        self._owner = owner
        self._chans: dict[int, _FakeChannel] = {}

    def __getitem__(self, index: int) -> _FakeChannel:
        if index not in self._chans:
            self._chans[index] = _FakeChannel(index, self._owner)
        return self._chans[index]


class FakePCA9685:
    """In-memory stand-in for ``adafruit_pca9685.PCA9685``."""

    #: The most recently constructed instance, for inspection in tests/REPL.
    last_instance: FakePCA9685 | None = None

    def __init__(self, i2c: object, address: int = 0x40) -> None:
        self.address = address
        self._frequency = 50
        self.channels = _FakeChannels(self)
        #: channel -> last duty cycle written
        self.duty: dict[int, int] = {}
        FakePCA9685.last_instance = self
        if _VERBOSE:
            print(f"[mockhw] PCA9685 @ 0x{address:02x}")

    @property
    def frequency(self) -> int:
        return self._frequency

    @frequency.setter
    def frequency(self, value: int) -> None:
        self._frequency = value
        if _VERBOSE:
            print(f"[mockhw] frequency = {value} Hz")

    def _on_write(self, channel: int, value: int) -> None:
        self.duty[channel] = value
        if _VERBOSE:
            period_us = 1_000_000.0 / self._frequency
            pulse_us = value / 65535.0 * period_us
            print(f"[mockhw] ch{channel}: duty={value:5d}  (~{pulse_us:4.0f} us)")

    def deinit(self) -> None:
        if _VERBOSE:
            print("[mockhw] deinit")


def install(verbose: bool = False) -> None:
    """Inject fake board/busio/adafruit_pca9685 modules into ``sys.modules``.

    Idempotent. After this, ``hardware.PCA9685Bus()`` runs without a Pi.
    """
    global _VERBOSE
    _VERBOSE = verbose

    board = types.ModuleType("board")
    board.SCL = "SCL"
    board.SDA = "SDA"

    busio = types.ModuleType("busio")

    class _FakeI2C:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def deinit(self) -> None:
            pass

    busio.I2C = _FakeI2C

    pca_mod = types.ModuleType("adafruit_pca9685")
    pca_mod.PCA9685 = FakePCA9685

    sys.modules["board"] = board
    sys.modules["busio"] = busio
    sys.modules["adafruit_pca9685"] = pca_mod


def uninstall() -> None:
    """Remove the fake modules (used by tests to avoid leaking into others)."""
    for name in ("board", "busio", "adafruit_pca9685"):
        sys.modules.pop(name, None)
