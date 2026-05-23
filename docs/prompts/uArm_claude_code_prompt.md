# Build a uArm Swift Control & Simulation Suite

I'm rebuilding the control software for a first-generation uArm Swift (servo-based, NOT the Pro). I no longer have the original control board, so I'm controlling the arm with a Raspberry Pi 4 + an Adafruit PCA9685 16-channel servo driver wired to the arm's 4 servo motors. I want a complete replacement for uArm Studio: Python API for scripting, inverse kinematics so I can command `(x, y, z)` Cartesian positions, a CLI for interactive control, a record/replay teach mode, and (later) a web UI.

**Two execution modes you must support throughout:**
- `UARM_MODE=sim` — pure software simulation, runs anywhere (your dev machine, CI). This is the default and what we'll use for iteration.
- `UARM_MODE=hardware` — drives the real PCA9685 over I²C. Only works on the Pi.

Develop in sim, then we'll validate on hardware together. **You can run commands locally but you do NOT have access to the actual Pi or arm.** Do not assume hardware tests have run — when I say "I tested on the Pi and X happens," believe me; when I haven't said it, assume hardware is untested.

---

## Working agreement

- Use `uv` for dependency management (`uv init`, `uv add`, `uv run`). If `uv` isn't installed, install it via the official one-liner.
- Use `pytest` for tests. Run tests after every meaningful change. Don't move to the next phase until the current phase's tests pass.
- Use `ruff` for linting and formatting. Run `ruff check --fix` and `ruff format` before declaring a phase done.
- Type-hint everything in Python. Run `mypy` if you set it up; not required.
- Commit at the end of each phase with a clear message. Don't commit broken code mid-phase.
- **Ask before running anything that touches hardware paths** (`/dev/i2c-*`, GPIO sysfs, anything importing `board` or `busio` for real). For pure-Python sim code, run freely.
- When you're uncertain about a fact (link lengths, joint limit signs, PCA9685 register details), say so explicitly and either ask me or web-search for primary sources. Don't fabricate.

Create a `CLAUDE.md` at the project root capturing these conventions plus the geometry constants, so future sessions inherit them.

---

## Hardware context (for when it runs on the Pi)

- **Raspberry Pi 4**, Raspberry Pi OS, Python 3.11+
- **Adafruit PCA9685** 16-channel PWM driver, I²C address `0x40`, connected to Pi pins SDA/SCL (GPIO 2/3)
- **External 5V/5A power supply** for the servos (NOT the Pi's 5V rail). Common ground between PSU and Pi/PCA9685.
- **4 servos** wired to PCA9685 channels:
  - Channel 0 = J0 (base rotation / yaw)
  - Channel 1 = J1 (shoulder / front linkage)
  - Channel 2 = J2 (elbow / rear linkage)
  - Channel 3 = J3 (wrist rotation / end-effector spin)

Each servo expects 50 Hz PWM with pulse widths roughly 500–2500 μs corresponding to 0–180°. Calibrate per-servo in code.

---

## The uArm Swift's mechanical geometry

This is critical — the uArm Swift is a **parallel-linkage** arm, not a serial arm. J1 and J2 don't compose like a typical 2-link arm; the linkage keeps the end-effector horizontal regardless of shoulder/elbow angles. Treat the geometry as:

- **Base height** (table to J1 axis): `H_BASE = 80 mm`
- **Upper arm length** (J1 axis to elbow): `L1 = 142 mm`
- **Forearm length** (elbow to wrist): `L2 = 158 mm`
- **End-effector horizontal offset** (wrist axis to tool tip): `L_TOOL = 56 mm`
- **Working envelope** (Cartesian, mm, base at origin):
  - X: ~140 to 320
  - Y: ~-200 to 200
  - Z: ~-50 to 150

These are approximate — put them in `config.py` as constants for me to tune after measuring.

**Joint limits**:
- J0 (base): -90° to +90° (0° = straight forward)
- J1 (shoulder): 0° to 135°
- J2 (elbow): 0° to 135°
- J3 (wrist): -90° to +90°
- Constraint: `J1 + J2 < ~180°`

---

## Inverse kinematics

Closed-form IK in `kinematics.py`. Given target `(x, y, z)` in mm and wrist orientation `wrist_deg`:

1. **Base angle**: `θ0 = atan2(y, x)`
2. **Reduce to 2D**: `r = sqrt(x² + y²) - L_TOOL`, `z' = z - H_BASE`
3. **2-link planar IK** for `(r, z')`:
   - `d² = r² + z'²`
   - `cos(α) = (L1² + L2² - d²) / (2·L1·L2)` → elbow internal angle
   - `cos(β) = (L1² + d² - L2²) / (2·L1·sqrt(d²))` → shoulder offset
   - `θ1 = atan2(z', r) + β`, `θ2 = π - α`
   - **Take the elbow-up branch** (positive root). The uArm can't reach elbow-down without colliding with the table.
4. Map to servo angles via per-servo calibration.
5. Raise `WorkspaceError` if `d > L1 + L2` or any joint limit is violated. Never silently clamp.

Implement forward kinematics too. Property test: `FK(IK(p)) ≈ p` to 0.1mm for 100 random reachable points. Use `hypothesis` if you like.

---

## Software architecture

Three layers, strictly separated:

### Layer 1: `hardware.py` — servo driver abstraction
- `class ServoBus(Protocol)`: `set_angle(channel, degrees)`, `get_angle(channel)`, `disable(channel)`
- `class PCA9685Bus`: real implementation using `adafruit-circuitpython-servokit`. Lazy-import the hardware libraries — they must not be importable on a dev machine without them installed.
- `class SimulatedBus`: in-memory, smoothly interpolates between target angles at a configurable max angular velocity (default 180°/sec). Records every command for inspection.
- Factory function `make_bus()` reads `UARM_MODE` and returns the right one.

### Layer 2: `arm.py` — high-level arm API
- `class UArm`:
  - `connect()`, `disconnect()`, `home()`
  - `set_joint_angles(j0, j1, j2, j3, speed=...)`
  - `set_position(x, y, z, wrist=0, speed=...)` — uses IK
  - `get_position()` — uses FK
  - `move_along(path, speed=...)` — waypoint list
  - `record_start()`, `record_stop()`, `replay(recording, speed_factor=1.0)`
  - `set_pump(on)`, `set_gripper(open)` — stub for now, log the call
- Long moves run in a background thread; expose a position callback for the UI.

### Layer 3: `cli.py` — Click or Typer CLI
**Build this BEFORE the web UI** — Claude Code can validate the API fast through it:
- `uarm home`
- `uarm goto X Y Z [--wrist DEG] [--speed N]`
- `uarm joints J0 J1 J2 J3`
- `uarm where` → prints current position and joint angles
- `uarm record NAME` → starts recording, Ctrl-C to stop and save
- `uarm play NAME [--speed-factor F]`
- `uarm list` → recordings on disk
- `uarm shell` → interactive REPL with the `UArm` instance bound as `arm`

### Layer 4: `server.py` + `static/` — FastAPI web app
Built across Phases 3 and 4:
- **Phase 3**: viz only. REST `GET /api/state`. WebSocket `/ws/live` streams position updates ~20 Hz. Single-page UI with Three.js arm rendering (CDN, no build step), mode indicator, position readout, ghost-target marker. No controls.
- **Phase 4**: REST endpoints mirroring the CLI. Joint sliders, Cartesian jog, go-to-position form, teach/replay panel.

---

## Simulation realism

The simulated bus must feel real enough that I trust UI behavior maps to hardware behavior:
- Servos have a max angular velocity (default 180°/s) — `set_angle` returns immediately, "current" angle slews toward target over time
- A background thread updates current angles at ~50 Hz
- Position callbacks fire during the slew, not just at the end
- Optional jitter mode (±0.5°) for stress-testing

---

## File / project structure

```
/uarm-suite/
├── CLAUDE.md                   # conventions + geometry constants (you write this)
├── pyproject.toml              # uv-managed
├── README.md                   # dev (sim) and Pi (hw) setup
├── config.py                   # LINK_PARAMS, joint limits, servo calibration
├── kinematics.py               # pure-function IK, FK, workspace checks
├── hardware.py                 # ServoBus, PCA9685Bus, SimulatedBus
├── arm.py                      # UArm high-level API
├── cli.py                      # Typer CLI
├── server.py                   # FastAPI (Phase 3)
├── static/                     # web UI (Phase 3 viz, Phase 4 controls)
├── tests/
│   ├── test_kinematics.py
│   ├── test_arm.py
│   └── test_cli.py
├── examples/
│   ├── draw_square.py
│   └── tic_tac_toe.py          # placeholder with TODO
└── recordings/                 # JSON files (gitignored)
```

---

## Phases — stop after each, run tests, show me the output, wait for my "go" before continuing

### Phase 1 — Kinematics, fully tested
- `config.py` + `kinematics.py`
- Unit tests: FK/IK round-trip, workspace boundaries, joint limits, unreachable target raises
- `uv run pytest tests/test_kinematics.py -v` must pass
- Show me the test output

### Phase 2 — Simulated arm + CLI
- `hardware.py` with `SimulatedBus`, `arm.py`, `cli.py`
- `uv run uarm goto 200 0 50` works, prints reached position
- `uv run uarm shell` opens a REPL where I can drive the arm
- Recording and replay work end-to-end against `SimulatedBus`
- `uv run pytest` all green

### Phase 3 — 3D visualization (read-only)
- FastAPI server + WebSocket `/ws/live` streaming sim state at ~20 Hz
- Single page with Three.js arm rendering (base, upper arm, forearm, end-effector) updating live from the WebSocket
- Orbit camera, zoom, reset-view button
- "Ghost target" translucent sphere at the last commanded `(x, y, z)` — lets me visually verify the tool tip reaches the target
- Mode indicator: amber "SIMULATION" or green "HARDWARE"
- Position readout (current `(x, y, z)` + joint angles, large, always visible)
- **No controls yet** — this phase exists to debug IK visually. CLI drives the arm; viz reflects state. That's it.
- `uv run uvicorn server:app --reload` works; opening localhost in a browser, then running `uarm goto 200 0 50` in another terminal, animates the arm to that point

### Phase 4 — Web UI controls
- Joint sliders (4, one per joint, with degree readouts)
- Cartesian jog panel (`±X`, `±Y`, `±Z`, `±wrist`, 5 mm or 5° per click, hold-to-repeat)
- Go-to-position form (validates via IK before sending; inline "out of reach" error)
- Teach/replay panel (Record / Stop / named save / list with Play and Delete)
- Console log (last 20 commands and responses)
- All controls drive the same `UArm` instance the CLI uses

### Phase 5 — Hardware path (deferred validation)
- `PCA9685Bus` implementation
- Lazy hardware imports so dev machine isn't broken
- README has Pi setup steps (enable I²C, install `adafruit-circuitpython-servokit`, wiring reference)
- **Don't run anything that imports hardware libs locally** — verify it compiles/imports only via mocked tests
- I'll validate on the Pi separately and report back

### Phase 6 — Stretch
- Per-servo calibration wizard in the UI
- Workspace visualization (reachable volume as translucent shape in the 3D view)
- Soft-limit toasts

**Rationale for the order:** the 3D viz is a debugging tool, not a feature. Without a real arm to look at, watching the sim move in 3D is the only way to catch IK bugs that don't show up as numeric test failures (wrong elbow branch, base rotation sign flip, calibration sign errors). Splitting viz (Phase 3) from controls (Phase 4) means each phase has a hard, demonstrable end state. Hardware comes last, after the math is visually verified.

---

## Things to get right

- **Joint angles ≠ servo angles** — they're related by per-servo calibration (zero offset, direction). Keep them strictly separated in the code. This is the #1 source of silent bugs.
- **Pick the elbow-up IK branch** — symptom of getting this wrong is the arm wanting to bend backward through the table.
- **Don't block FastAPI on long moves** — threads, not async-on-blocking.
- **Safety**: on startup, slow-home (max 30°/s) to a known pose. Never snap.
- **No silent clamping** — out-of-workspace or joint-limit violations raise; the UI/CLI shows the error.

---

## What I do NOT want

- No Docker, no microservices — single process
- No frontend build step (vanilla JS + CDN Three.js is fine)
- No auth, no database
- Don't pull in the official uArm Python SDK — we're replacing it

---

## Starting point

Read this prompt fully. Then write `CLAUDE.md` and stop. I'll review it before you start Phase 1 — that's a checkpoint to confirm you understood the geometry and constraints.

If anything in the geometry section is wrong, say so and propose corrected values with reasoning. I can measure my actual arm.
