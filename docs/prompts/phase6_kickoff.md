# Phase 6 kickoff prompt

## Where we are

Phases 1–5 are committed. The repo now contains:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml
├── conftest.py
├── config.py              geometry, joint limits, channel map, servo calibration
├── kinematics.py           FK/IK, WorkspaceError, JointLimitError, check_joint_limits
├── hardware.py             ServoBus protocol, SimulatedBus, PCA9685Bus, calibration helpers
├── arm.py                  UArm class: motion, recording/replay, callbacks
├── cli.py                  Typer CLI (server-aware)
├── server.py               FastAPI: REST + WebSocket + recording/replay endpoints
├── static/
│   ├── index.html          Three.js viz + control panel layout
│   ├── viz.js              3D arm model + WebSocket + OrbitControls
│   ├── app.js              Control panel: sliders, jog, goto, teach/replay
│   └── style.css           dark theme, controls, toasts
├── tests/
│   ├── test_kinematics.py  20 tests
│   ├── test_arm.py         18 tests
│   ├── test_cli.py         14 tests
│   ├── test_server.py      13 tests
│   └── test_hardware.py    22 tests
├── README.md               quick start + hardware setup docs
└── docs/
    ├── prompts/
    └── walkthroughs/
```

87 tests passing, lint clean.

## Lessons from Phase 5

1. **`joint_to_servo()` and `servo_to_joint()` are module-level functions.**
   They live in `hardware.py` and use `SERVO_CALIBRATION` from config.
   Any calibration wizard should read/write `SERVO_CALIBRATION` and use
   these functions to preview the effect.

2. **PCA9685Bus slews PWM inside the tick loop.** All I2C writes happen
   on the background thread (50Hz) under `self._lock`. `immediate=True`
   also writes PWM under the lock. The calibration wizard should NOT
   bypass the bus — use `set_angle(immediate=True)` for instant moves.

3. **Mock strategy for PCA9685Bus tests.** The fixture `hw_mocks` in
   `test_hardware.py` patches `sys.modules` with fake board/busio/
   adafruit_pca9685 modules and yields mock objects. Tests that need
   PCA9685Bus should use this pattern. The `_Channel` class provides a
   minimal `duty_cycle` attribute.

4. **PWM duty cycle formula.** For 50Hz (20000μs period):
   `duty_cycle = int(pulse_us / 20000 * 65535)` where
   `pulse_us = min_us + (servo_deg / 180) * (max_us - min_us)`.
   Known values: joint 0° → duty 4915, joint -90° → duty 1638,
   joint 90° → duty 8191.

5. **README exists.** It covers sim quick start, hardware wiring,
   PCA9685 config, Pi software install, safety notes, and architecture.
   Phase 6 additions should extend it, not replace it.

## What to do in Phase 6

Per CLAUDE.md, Phase 6 is stretch goals: "calibration wizard, workspace
viz, soft-limit toasts."

### Calibration wizard

- Interactive CLI or web UI flow to tune `SERVO_CALIBRATION` per-servo
- Steps: (1) manually move each joint to its 0° reference position,
  (2) record the servo angle at that position → `zero_deg`,
  (3) move joint in the positive direction → determine `direction`,
  (4) optionally sweep to find `min_us`/`max_us` limits
- Write updated values to `config.py` or a separate `calibration.json`

### Workspace visualization

- Render the reachable workspace as a translucent volume in the 3D viz
- Precompute a point cloud from FK over the joint-limit ranges
- Show the convex hull or a simplified torus-sector mesh
- Highlight when the target is near or outside the workspace boundary

### Soft-limit toasts

- When joint angles approach limits (within 5° of a boundary), show
  a warning toast in the web UI
- When the coupled parallelogram constraint is near violation, show
  a specific warning
- Color the affected joint slider yellow/red as it approaches limits

### Key constraints

- All existing tests must continue passing
- Calibration wizard must work in both sim and hardware modes
- No npm/build step — keep vanilla JS
- Don't touch hardware without explicit go-ahead

1 extra tasks not present in the original claude.md file: 
- this project started as a fun project with my kid to create a tic-tac-toe game with the uarm swift i have. now that the app to control the arm is complete, help me add a tic-tac-toe simulation and the hardware control so I can play with that. Plan it so we can add more scripts for different games or activities using the uarm seamlessly. Only create a prompt for a stretch phase 7 do not execute it