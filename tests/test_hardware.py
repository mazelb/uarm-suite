"""Tests for PCA9685Bus — all mocked, no real hardware required."""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock hardware modules
# ---------------------------------------------------------------------------


class _Channel:
    """Minimal stand-in for a PCA9685 channel."""

    duty_cycle: int = 0


@pytest.fixture()
def hw_mocks():
    """Inject fake board/busio/adafruit_pca9685 into sys.modules.

    Yields a dict with the mock objects so tests can inspect them.
    """
    mock_board = MagicMock()
    mock_board.SCL = "SCL"
    mock_board.SDA = "SDA"

    mock_busio = MagicMock()

    mock_pca9685_mod = MagicMock()
    mock_pca = MagicMock()
    mock_pca.channels = defaultdict(_Channel)
    mock_pca9685_mod.PCA9685.return_value = mock_pca

    mods = {
        "board": mock_board,
        "busio": mock_busio,
        "adafruit_pca9685": mock_pca9685_mod,
    }
    with patch.dict(sys.modules, mods):
        yield {
            "board": mock_board,
            "busio": mock_busio,
            "pca9685_mod": mock_pca9685_mod,
            "pca": mock_pca,
        }


def _make_bus(hw_mocks: dict, **kwargs):  # noqa: ANN001
    """Create a PCA9685Bus with mocked hardware."""
    from hardware import PCA9685Bus

    return PCA9685Bus(**kwargs)


# ---------------------------------------------------------------------------
# Lazy import
# ---------------------------------------------------------------------------


def test_import_hardware_without_hw_packages():
    """Importing the hardware module must work even when board/busio are absent."""
    import hardware  # noqa: F401

    assert hasattr(hardware, "PCA9685Bus")
    assert hasattr(hardware, "SimulatedBus")


def test_pca9685_missing_packages_raises():
    """PCA9685Bus.__init__ raises RuntimeError when hw packages are missing."""
    from hardware import PCA9685Bus

    with pytest.raises(RuntimeError, match="adafruit-circuitpython-pca9685"):
        PCA9685Bus()


# ---------------------------------------------------------------------------
# Calibration conversion
# ---------------------------------------------------------------------------


def test_joint_to_servo_identity_calibration():
    """With default calibration (zero_deg=90, direction=+1), joint 0 → servo 90."""
    from hardware import joint_to_servo

    assert joint_to_servo(0, 0.0) == 90.0
    assert joint_to_servo(0, 45.0) == 135.0
    assert joint_to_servo(0, -45.0) == 45.0
    assert joint_to_servo(0, 90.0) == 180.0
    assert joint_to_servo(0, -90.0) == 0.0


def test_servo_to_joint_identity_calibration():
    """Reverse of joint_to_servo."""
    from hardware import servo_to_joint

    assert servo_to_joint(0, 90.0) == 0.0
    assert servo_to_joint(0, 135.0) == 45.0
    assert servo_to_joint(0, 45.0) == -45.0


def test_joint_servo_roundtrip():
    """joint→servo→joint must be identity."""
    from hardware import joint_to_servo, servo_to_joint

    for ch in range(4):
        for deg in (-90, -45, 0, 45, 90):
            servo = joint_to_servo(ch, float(deg))
            joint = servo_to_joint(ch, servo)
            assert abs(joint - deg) < 1e-9, f"ch={ch}, deg={deg}"


def test_joint_to_servo_reversed_direction():
    """With direction=-1, increasing joint angle decreases servo angle."""
    from config import SERVO_CALIBRATION
    from hardware import joint_to_servo, servo_to_joint

    orig = SERVO_CALIBRATION[1].copy()
    try:
        SERVO_CALIBRATION[1] = {
            "min_us": 500,
            "max_us": 2500,
            "zero_deg": 90.0,
            "direction": -1,
        }
        assert joint_to_servo(1, 0.0) == 90.0
        assert joint_to_servo(1, 45.0) == 45.0
        assert joint_to_servo(1, -45.0) == 135.0
        assert servo_to_joint(1, 45.0) == 45.0
        assert servo_to_joint(1, 135.0) == -45.0
    finally:
        SERVO_CALIBRATION[1] = orig


def test_joint_to_servo_uncalibrated_channel():
    """Channels not in SERVO_CALIBRATION pass through unchanged."""
    from hardware import joint_to_servo, servo_to_joint

    assert joint_to_servo(99, 42.0) == 42.0
    assert servo_to_joint(99, 42.0) == 42.0


# ---------------------------------------------------------------------------
# PWM duty-cycle calculation
# ---------------------------------------------------------------------------


def test_pwm_duty_cycle_at_joint_zero(hw_mocks):
    """Joint 0° → servo 90° → midpoint pulse → expected duty cycle."""
    bus = _make_bus(hw_mocks)
    try:
        bus.set_angle(0, 0.0, immediate=True)
        ch0 = hw_mocks["pca"].channels[0]
        # servo 90° → pulse = 500 + (90/180)*(2500-500) = 1500 μs
        # duty = int(1500/20000 * 65535) = 4915
        assert ch0.duty_cycle == 4915
    finally:
        bus._running = False
        bus.close()


def test_pwm_duty_cycle_at_extremes(hw_mocks):
    """Joint ±90° → servo 0°/180° → min/max pulse."""
    bus = _make_bus(hw_mocks)
    try:
        bus.set_angle(0, -90.0, immediate=True)
        ch0 = hw_mocks["pca"].channels[0]
        # servo 0° → 500 μs → int(500/20000*65535) = 1638
        assert ch0.duty_cycle == 1638

        bus.set_angle(0, 90.0, immediate=True)
        # servo 180° → 2500 μs → int(2500/20000*65535) = 8191
        assert ch0.duty_cycle == 8191
    finally:
        bus._running = False
        bus.close()


# ---------------------------------------------------------------------------
# Speed limiting / slew
# ---------------------------------------------------------------------------


def test_slew_rate_limiting(hw_mocks):
    """Angle should slew at max_dps, not jump instantly."""
    bus = _make_bus(hw_mocks, max_deg_per_sec=180.0)
    try:
        bus.set_angle(0, 90.0)
        time.sleep(0.15)
        angle = bus.get_angle(0)
        assert 0.0 < angle < 90.0, f"angle should be mid-slew, got {angle}"
    finally:
        bus._running = False
        bus.close()


def test_slew_reaches_target(hw_mocks):
    """After enough time, the angle should reach the target."""
    bus = _make_bus(hw_mocks, max_deg_per_sec=360.0)
    try:
        bus.set_angle(0, 45.0)
        time.sleep(0.5)
        angle = bus.get_angle(0)
        assert abs(angle - 45.0) < 1.0, f"expected ~45°, got {angle}"
    finally:
        bus._running = False
        bus.close()


def test_speed_change_affects_slew(hw_mocks):
    """Changing speed mid-slew should affect the rate."""
    bus = _make_bus(hw_mocks, max_deg_per_sec=90.0)
    try:
        bus.set_angle(0, 90.0)
        time.sleep(0.1)
        slow_progress = bus.get_angle(0)

        bus._current[0] = 0.0
        bus.set_speed(360.0)
        time.sleep(0.1)
        fast_progress = bus.get_angle(0)

        assert fast_progress > slow_progress * 1.5
    finally:
        bus._running = False
        bus.close()


# ---------------------------------------------------------------------------
# Listener callbacks
# ---------------------------------------------------------------------------


def test_listener_fires_during_slew(hw_mocks):
    """Listeners should receive snapshots as the bus ticks."""
    bus = _make_bus(hw_mocks)
    snapshots: list[dict[int, float]] = []
    bus.add_listener(lambda s: snapshots.append(s))
    try:
        bus.set_angle(0, 45.0)
        time.sleep(0.15)
        assert len(snapshots) >= 2, f"expected multiple callbacks, got {len(snapshots)}"
        assert 0 in snapshots[-1]
    finally:
        bus._running = False
        bus.close()


# ---------------------------------------------------------------------------
# Immediate mode
# ---------------------------------------------------------------------------


def test_immediate_snaps_position(hw_mocks):
    """immediate=True should snap the tracked position instantly."""
    bus = _make_bus(hw_mocks)
    try:
        bus.set_angle(0, 90.0, immediate=True)
        assert bus.get_angle(0) == 90.0
    finally:
        bus._running = False
        bus.close()


def test_immediate_writes_pwm(hw_mocks):
    """immediate=True should write PWM without waiting for tick loop."""
    bus = _make_bus(hw_mocks)
    try:
        bus.set_angle(1, 45.0, immediate=True)
        ch1 = hw_mocks["pca"].channels[1]
        assert ch1.duty_cycle > 0
    finally:
        bus._running = False
        bus.close()


# ---------------------------------------------------------------------------
# Disable / close
# ---------------------------------------------------------------------------


def test_disable_zeros_duty_cycle(hw_mocks):
    """disable() should set duty cycle to 0 for the channel."""
    bus = _make_bus(hw_mocks)
    try:
        bus.set_angle(0, 45.0, immediate=True)
        assert hw_mocks["pca"].channels[0].duty_cycle > 0
        bus.disable(0)
        assert hw_mocks["pca"].channels[0].duty_cycle == 0
    finally:
        bus._running = False
        bus.close()


def test_close_stops_thread_and_deinits(hw_mocks):
    """close() should stop the tick loop, zero channels, and deinit I2C."""
    bus = _make_bus(hw_mocks)
    bus.set_angle(0, 45.0, immediate=True)
    time.sleep(0.05)
    bus.close()
    assert not bus._running
    assert bus._thread is None
    hw_mocks["pca"].deinit.assert_called_once()


# ---------------------------------------------------------------------------
# get_angle
# ---------------------------------------------------------------------------


def test_get_angle_default_zero(hw_mocks):
    """Unset channels return 0.0."""
    bus = _make_bus(hw_mocks)
    try:
        assert bus.get_angle(0) == 0.0
        assert bus.get_angle(7) == 0.0
    finally:
        bus._running = False
        bus.close()


# ---------------------------------------------------------------------------
# Integration with make_bus
# ---------------------------------------------------------------------------


def test_make_bus_sim_default():
    """make_bus() with no args returns SimulatedBus (UARM_MODE defaults to sim)."""
    from hardware import SimulatedBus, make_bus

    bus = make_bus()
    assert isinstance(bus, SimulatedBus)
    bus.close()


def test_make_bus_hardware_mode(hw_mocks):
    """make_bus('hardware') returns PCA9685Bus."""
    from hardware import PCA9685Bus, make_bus

    bus = make_bus("hardware")
    assert isinstance(bus, PCA9685Bus)
    bus.close()


def test_make_bus_invalid_mode():
    """make_bus('bogus') raises ValueError."""
    from hardware import make_bus

    with pytest.raises(ValueError, match="bogus"):
        make_bus("bogus")


# ---------------------------------------------------------------------------
# PWM writes happen on tick
# ---------------------------------------------------------------------------


def test_tick_loop_writes_pwm_during_slew(hw_mocks):
    """The tick loop should write increasing duty cycles as it slews."""
    bus = _make_bus(hw_mocks, max_deg_per_sec=180.0)
    try:
        bus.set_angle(0, 45.0)
        time.sleep(0.15)
        ch0 = hw_mocks["pca"].channels[0]
        # After slewing from 0 toward 45, duty cycle should be > the zero-angle value
        zero_duty = 4915  # joint 0° → servo 90° → 1500μs
        assert ch0.duty_cycle > zero_duty
    finally:
        bus._running = False
        bus.close()
