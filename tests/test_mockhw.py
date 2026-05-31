"""Tests for mock-hardware mode — runs the real PCA9685Bus path without a Pi."""

from __future__ import annotations

import pytest

import mockhw


@pytest.fixture
def mock_installed():
    """Install fake hw modules, then remove them so they don't leak to other tests."""
    mockhw.install(verbose=False)
    try:
        yield
    finally:
        mockhw.uninstall()


def test_make_bus_mock_returns_real_pca_bus(mock_installed):
    from hardware import PCA9685Bus, make_bus

    bus = make_bus("mock")
    try:
        assert isinstance(bus, PCA9685Bus)
    finally:
        bus.close()


def test_mock_bus_writes_duty_cycles(mock_installed):
    from hardware import make_bus

    bus = make_bus("mock")
    try:
        bus.set_angle(0, 0.0, immediate=True)
        # Joint 0° → servo 90° → 1500 us → duty 4915 (same math as real hardware).
        assert mockhw.FakePCA9685.last_instance.duty[0] == 4915
    finally:
        bus.close()


def test_full_stack_through_mock(mock_installed, monkeypatch: pytest.MonkeyPatch):
    """UArm + IK + PCA9685Bus end-to-end on the dev box; all joints get PWM."""
    monkeypatch.setattr("arm.SLOW_HOME_DEG_PER_SEC", 100000.0)
    monkeypatch.setattr("arm.DEFAULT_DEG_PER_SEC", 100000.0)
    from arm import UArm
    from hardware import make_bus

    arm = UArm(bus=make_bus("mock")).connect()
    try:
        arm.home(blocking=True)
        arm.set_position(250, 0, 50, blocking=True)
        duty = mockhw.FakePCA9685.last_instance.duty
        for ch in range(4):  # J0..J3 all driven
            assert duty.get(ch, 0) > 0
    finally:
        arm.disconnect()
