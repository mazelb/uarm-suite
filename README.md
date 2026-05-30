# uArm Swift Control Suite

A complete replacement for uArm Studio targeting a first-generation uArm Swift
(servo-based, not the Pro). The original control board is removed; control
happens via a Raspberry Pi 4 + Adafruit PCA9685 16-channel servo driver.

## Quick start (simulation)

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -v

# Start the web server (sim mode, default)
uv run python server.py
# Open http://localhost:8000 in your browser

# Or use the CLI
uv run python cli.py home
uv run python cli.py goto 200 0 50
uv run python cli.py joints 0 45 -45 0
```

## Activities

Arm-driven activities (games, drawing) live in the `activities/` package and are
auto-discovered — drop a new module in there and it shows up everywhere, no core
arm code to touch.

```bash
uv run uarm activity list                       # what's available
uv run uarm activity run tic-tac-toe            # play in the terminal (you are X)
uv run uarm activity run draw-shapes -o shape=star -o size=40
```

In the web UI, the **Activities** panel (top of Controls) has a clickable
tic-tac-toe board and a shape-drawer; both animate the 3D arm. When the server is
running, the CLI forwards to it so the terminal game and the browser share one arm.

Two flavours, both behind one registry:
- **Runnable** (e.g. draw-shapes) — `setup` → `run` → `cleanup`, runs to completion.
- **Interactive** (e.g. tic-tac-toe) — a stateful session driven turn by turn via
  `start` / `human_move` / `state`.

The tic-tac-toe AI is unbeatable (minimax). Drawing commands the tool-tip Cartesian
position as the pen contact point and lifts between strokes; on hardware the pen
mount offset is absorbed into Z calibration. See `docs/walkthroughs/phase7.md`.

## Hardware setup

### Components

- Raspberry Pi 4 (any RAM variant)
- Adafruit PCA9685 16-channel PWM/servo driver
- uArm Swift (first-generation, servo-based)
- 5V 4A+ power supply for servos (do NOT power servos from the Pi)
- 4x jumper wires for I2C

### Wiring

Connect the PCA9685 to the Raspberry Pi's I2C bus:

| PCA9685 pin | Raspberry Pi pin | Description        |
|-------------|------------------|--------------------|
| VCC         | Pin 1 (3.3V)     | Logic power        |
| GND         | Pin 6 (GND)      | Ground             |
| SDA         | Pin 3 (GPIO 2)   | I2C data           |
| SCL         | Pin 5 (GPIO 3)   | I2C clock          |
| V+          | External 5V PSU  | Servo power (4A+)  |

Connect the uArm Swift servos to PCA9685 channels:

| Channel | Joint     | Description          |
|---------|-----------|----------------------|
| 0       | J0        | Base rotation (yaw)  |
| 1       | J1        | Shoulder             |
| 2       | J2        | Elbow                |
| 3       | J3        | Wrist rotation       |
| 4       | PUMP      | Suction pump (stub)  |
| 5       | GRIPPER   | Gripper (stub)       |

### PCA9685 configuration

- I2C address: `0x40` (default)
- PWM frequency: 50 Hz
- Pulse range: 500–2500 μs (0–180°)

### Software install on the Pi

```bash
# Enable I2C
sudo raspi-config  # Interface Options → I2C → Enable

# Verify the PCA9685 is detected
sudo i2cdetect -y 1
# Should show device at address 0x40

# Install CircuitPython libraries
pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit

# Clone and install
git clone <repo-url> uarm-suite && cd uarm-suite
uv sync
```

### Running on hardware

```bash
# Start the server in hardware mode
UARM_MODE=hardware uv run python server.py

# Or use the CLI
UARM_MODE=hardware uv run python cli.py home
UARM_MODE=hardware uv run python cli.py goto 200 0 50
```

### Safety notes

1. **Power sequencing.** Connect the servo power supply BEFORE starting the
   software. Servos with no power will not hold position, and the arm may
   drop under its own weight.

2. **Slow-home on startup.** The arm always homes at 30°/s maximum on first
   connect. This prevents sudden jerks from an unknown position. Never bypass
   the homing sequence.

3. **Servo calibration.** The default `SERVO_CALIBRATION` in `config.py` uses
   identity values (zero_deg=90, direction=+1). You MUST tune these against
   the physical arm:
   - `zero_deg`: the servo angle (0–180°) where the joint reads 0°
   - `direction`: +1 if joint and servo turn the same way, -1 if reversed
   - `min_us` / `max_us`: pulse widths for servo 0° and 180°

4. **Joint limits.** The software enforces joint limits and raises errors for
   out-of-range targets. Do not disable these checks on real hardware.

5. **Emergency stop.** Kill the process (Ctrl+C) to immediately stop all
   servo PWM output. The `close()` handler zeros all channels on shutdown.

## Architecture

```
┌──────────────────────────────────────────┐
│  cli.py / server.py                      │  ← user-facing
├──────────────────────────────────────────┤
│  arm.py — UArm class, threading, record  │  ← high-level
├──────────────────────────────────────────┤
│  hardware.py — ServoBus protocol         │  ← driver
│    SimulatedBus (default, no hardware)   │
│    PCA9685Bus   (UARM_MODE=hardware)     │
└──────────────────────────────────────────┘
        ↑
   kinematics.py — pure FK/IK functions
   config.py     — geometry + calibration constants
```

## Environment variables

| Variable    | Values            | Default | Description               |
|-------------|-------------------|---------|---------------------------|
| `UARM_MODE` | `sim`, `hardware` | `sim`   | Bus implementation to use |

## Tests

```bash
uv run pytest -v          # all tests
uv run pytest -v -k pca   # PCA9685Bus tests only
uv run ruff check --fix . # lint
uv run ruff format .      # format
```
