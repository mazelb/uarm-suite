# Phase 5 kickoff prompt

## Where we are

Phases 1–4 are committed. The repo now contains:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml
├── conftest.py
├── config.py              geometry, joint limits, channel map, servo calibration
├── kinematics.py           FK/IK, WorkspaceError, JointLimitError, check_joint_limits
├── hardware.py             ServoBus protocol, SimulatedBus, PCA9685Bus stub
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
│   └── test_server.py      13 tests
└── docs/
    ├── prompts/
    ├── reports/
    └── walkthroughs/
```

65 tests passing, lint clean.

## Lessons from Phase 4

1. **`check_joint_limits` is now public.** Renamed from `_check_joint_limits`
   in kinematics.py so the server can validate joint angles before sending
   them to `arm.set_joint_angles()` (which doesn't validate internally).
   Phase 5 should use this function for any new validation paths.

2. **WebSocket state includes `recording` flag.** `_state_dict()` now
   returns `{"recording": bool, ...}` so the frontend can sync the
   Record/Stop button state. If Phase 5 adds more arm state (e.g., pump
   or gripper state), extend `_state_dict()`.

3. **Server tests use `tmp_path` for recordings.** The test fixture
   monkeypatches `arm.RECORDINGS_DIR` and `server.RECORDINGS_DIR` to
   `tmp_path / "recordings"` to avoid polluting the real recordings
   directory. Follow this pattern for any new filesystem-touching tests.

4. **Frontend is vanilla JS with no build step.** `app.js` uses `fetch()`
   for REST calls and a second WebSocket connection for state sync (separate
   from viz.js). Both reconnect on close. Any new frontend code should
   follow the same pattern — no npm, no bundler.

5. **Toast notifications for errors.** `showToast(msg, type, duration)`
   is available in `app.js`. Types: `"error"` (red, default), `"info"`
   (blue), `"success"` (green). Duration defaults to 4 seconds. Use this
   for any new error surfaces.

## What to do in Phase 5

Per CLAUDE.md, Phase 5 is "`PCA9685Bus`, README hardware setup." **Done when:**

- `PCA9685Bus` in `hardware.py` is fully implemented:
  - Lazy imports of `board`, `busio`, `adafruit_pca9685` (Rule 1)
  - Reads `UARM_MODE=hardware` to activate (Rule 2)
  - Joint-to-servo angle conversion via `SERVO_CALIBRATION` (Rule 3)
  - Background thread for servo slew simulation (matching SimulatedBus)
  - Listener callbacks for position updates
  - `set_speed()`, `get_angle()`, `set_angle()`, `close()` implemented
- Mocked tests pass — tests that verify the PCA9685Bus logic WITHOUT
  requiring actual hardware (mock the `adafruit_pca9685` imports)
- README has a hardware setup section:
  - Raspberry Pi 4 wiring diagram / pin table
  - PCA9685 I2C address, PWM frequency
  - Package install: `adafruit-circuitpython-pca9685`, `adafruit-circuitpython-servokit`
  - `UARM_MODE=hardware uv run python server.py` example
  - Safety notes: slow-home, power sequencing
- All existing tests still pass (sim mode unaffected)
- Walkthrough, report, and Phase 6 kickoff committed

### Key constraints

- **Do NOT run hardware-touching code** (Rule 8). All PCA9685Bus tests
  must mock the hardware imports. Maz will test on the Pi.
- **Joint ≠ servo angles** (Rule 3). The `SERVO_CALIBRATION` dict maps
  joint angles to servo angles via `zero_deg` and `direction`. The bus
  must apply this conversion in both directions.
- **Lazy imports** (Rule 1). `import board`, `import busio`, etc. must
  happen inside `PCA9685Bus.__init__` or a classmethod, never at module
  top level. The dev machine must work without these packages installed.

### Test suggestions

- `test_pca9685_lazy_import` — verify that `import hardware` works even
  when `board`/`busio` are not installed
- `test_pca9685_calibration_conversion` — verify joint→servo and
  servo→joint angle conversion against known values
- `test_pca9685_speed_limiting` — verify slew rate limiting
- `test_pca9685_listener_callback` — verify listener fires during slew
- Mock strategy: `unittest.mock.patch.dict('sys.modules', ...)` to inject
  fake `board`, `busio`, `adafruit_pca9685` modules
