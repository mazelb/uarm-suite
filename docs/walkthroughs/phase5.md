# Phase 5 Walkthrough — PCA9685Bus + README Hardware Setup

## Prerequisites

- Phases 1–4 committed, all tests passing.
- Python venv via `uv`.

## 1. Run tests

```bash
uv run pytest -v
```

**Expected:** 87 tests pass (20 kinematics, 18 arm, 14 CLI, 13 server,
22 hardware).

## 2. Verify lazy import

```bash
uv run python -c "import hardware; print('OK')"
```

**Expected:** Prints `OK`. The `hardware` module imports without `board`,
`busio`, or `adafruit_pca9685` installed. These are only imported inside
`PCA9685Bus.__init__`.

## 3. Verify PCA9685Bus requires hardware packages

```bash
uv run python -c "from hardware import PCA9685Bus; PCA9685Bus()"
```

**Expected:** `RuntimeError: PCA9685Bus requires adafruit-circuitpython-pca9685,
board, and busio. Install them on the Raspberry Pi.`

## 4. Verify calibration conversion

```bash
uv run python -c "
from hardware import joint_to_servo, servo_to_joint

# Default calibration: zero_deg=90, direction=+1
print('joint  0 -> servo', joint_to_servo(0, 0.0))    # 90.0
print('joint 45 -> servo', joint_to_servo(0, 45.0))   # 135.0
print('joint -90 -> servo', joint_to_servo(0, -90.0)) # 0.0

# Roundtrip
print('servo 135 -> joint', servo_to_joint(0, 135.0)) # 45.0
"
```

**Expected output:**
```
joint  0 -> servo 90.0
joint 45 -> servo 135.0
joint -90 -> servo 0.0
servo 135 -> joint 45.0
```

## 5. Run PCA9685Bus-specific tests

```bash
uv run pytest tests/test_hardware.py -v
```

**Expected:** 22 tests pass, covering:
- Lazy import (module loads without hw packages)
- Missing-package error message
- Joint↔servo calibration conversion (identity, reversed, uncalibrated)
- PWM duty cycle calculation at 0°, ±90°
- Slew rate limiting (mid-slew angle check)
- Slew reaches target
- Speed change affects slew rate
- Listener callbacks fire during slew
- Immediate mode snaps position and writes PWM
- Disable zeros duty cycle
- Close stops thread and calls deinit
- Default angle is 0.0
- make_bus returns correct type for each mode

## 6. Verify sim mode is unaffected

```bash
uv run python server.py &
sleep 2
curl -s http://localhost:8000/api/state | python -m json.tool
kill %1
```

**Expected:** Server starts normally in sim mode. The `/api/state` endpoint
returns JSON with joint angles and position. All existing functionality
(CLI, web UI, 3D viz) works exactly as before.

## 7. Check README

Open `README.md` and verify it contains:
- Quick start (sim mode)
- Hardware setup: wiring table, PCA9685 config, Pi software install
- `UARM_MODE=hardware` usage examples
- Safety notes (power sequencing, slow-home, calibration, emergency stop)

## What you should NOT see yet

- **No real hardware control.** PCA9685Bus is implemented and tested via
  mocks, but has not been tested on actual hardware. Maz must run it on the
  Pi to verify.
- **No calibration wizard.** Servo calibration values in `config.py` are
  identity defaults. Tuning is a manual edit for now (Phase 6 stretch goal).
- **No workspace visualization.** The 3D viz doesn't show reachable volume
  (Phase 6 stretch goal).

## Hardware testing (for Maz on the Pi)

When ready to test on the Raspberry Pi:

1. Wire the PCA9685 per the README wiring table.
2. Install CircuitPython packages:
   ```bash
   pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit
   ```
3. Verify I2C:
   ```bash
   sudo i2cdetect -y 1
   # Should show 0x40
   ```
4. Test with a single servo first:
   ```bash
   UARM_MODE=hardware uv run python -c "
   from hardware import make_bus
   bus = make_bus('hardware')
   bus.set_angle(0, 0.0, immediate=True)  # Move J0 to 0°
   import time; time.sleep(2)
   bus.set_angle(0, 45.0, immediate=True)  # Move J0 to 45°
   time.sleep(2)
   bus.close()
   "
   ```
5. If that works, try the full arm:
   ```bash
   UARM_MODE=hardware uv run python cli.py home
   ```
6. Tune `SERVO_CALIBRATION` in `config.py` as needed.
