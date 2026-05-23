# CLAUDE.md — uArm Swift Control Suite

Standing instructions and project context. Read this first every session.

## What this project is

A complete replacement for uArm Studio targeting a **first-generation uArm Swift** (servo-based, NOT the Pro). The original control board is gone; control happens via a **Raspberry Pi 4 + Adafruit PCA9685 16-channel servo driver** wired to the arm's 4 servos.

Deliverables: Python API, CLI, inverse kinematics, record/replay teach mode, and (later) a web UI.

## Hard rules

1. **Hardware libraries are lazy-imported.** Anything that imports `board`, `busio`, `adafruit_pca9685`, or `adafruit_servokit` only loads inside `PCA9685Bus`, never at module top level. The dev machine must work without them installed.
2. **`UARM_MODE` env var selects the bus.** Default is `sim`. `hardware` is opt-in.
3. **Joint angles ≠ servo angles.** They differ by per-servo calibration (zero offset + direction). Never conflate them. This is the #1 source of silent bugs in this codebase.
4. **Elbow-up IK only.** The cosine-law branch with the positive root. Elbow-down configurations collide with the table.
5. **Never silently clamp.** Out-of-workspace targets or joint-limit violations raise `WorkspaceError` or `JointLimitError`. The CLI/UI surfaces the error.
6. **No blocking on long moves.** `set_position` and `move_along` run in a background thread. FastAPI handlers must stay responsive.
7. **Slow-home on startup.** Max 30°/s to a known safe pose. Never snap servos to position from an unknown state.
8. **Ask before running hardware-touching code.** Anything that opens `/dev/i2c-*`, writes GPIO, or imports `board`/`busio` for real requires my explicit "go" first. Pure sim code: run freely.
9. **Don't fabricate hardware test results.** I run hardware tests on the Pi. When I haven't said "I ran it on the Pi and X," assume hardware is untested.
10. **Don't pull in the official uArm Python SDK.** We're replacing it, not depending on it.

## Tooling

- **Package manager:** `uv`. Use `uv init`, `uv add <pkg>`, `uv run <cmd>`. Install via the official one-liner if missing.
- **Tests:** `pytest`. `uv run pytest -v` should pass before declaring any phase done.
- **Property tests:** `hypothesis` for IK round-trip testing.
- **Lint/format:** `ruff`. Run `ruff check --fix` and `ruff format` before committing.
- **Types:** type-hint everything in Python. `mypy` optional.
- **Commits:** one commit per completed phase. Clear messages. Don't commit broken code mid-phase.
- **Walkthroughs:** every completed phase must produce or extend `docs/walkthroughs/phase<N>.md` — a step-by-step manual validation guide Maz can follow to confirm what the phase delivered. Exact commands, exact expected outputs, plus a short "what you should NOT see yet" list of deferred behavior. The walkthrough is part of the phase, not optional polish.

## Geometry constants (canonical — copy into `config.py`)

The uArm Swift is a **parallel-linkage arm**, not a serial 2-link. J1 and J2 don't compose like a textbook two-link planar arm — the parallelogram linkage keeps the end-effector horizontal regardless of shoulder/elbow angles. IK derivation assumes this.

```python
# All in mm
H_BASE = 80         # table to J1 axis
L1     = 142        # J1 axis to elbow
L2     = 158        # elbow to wrist
L_TOOL = 56         # wrist axis to tool tip (horizontal in arm plane)

# Workspace (approximate, base at origin, Z=0 = table)
X_RANGE = (140, 320)
Y_RANGE = (-200, 200)
Z_RANGE = (-50, 150)
```

These are **estimates**. Maz will measure the actual arm and update them.

## Joint angle convention

Joint angles in code are **logical** angles, not servo angles (they map to servo angles via `SERVO_CALIBRATION`).

- `j0` — base rotation about vertical. `j0 = 0` points along +X.
- `j1` — **upper-arm absolute angle from horizontal**. `j1 = 0` is horizontal, `j1 = 90` is straight up.
- `j2` — **forearm absolute angle from horizontal**. `j2 = 0` is horizontal, `j2 > 0` tilts wrist above elbow, `j2 < 0` tilts wrist below elbow. **NOT the elbow bend angle.** This matches how the parallel linkage is actually driven — both servos set absolute segment angles.
- `j3` — wrist rotation about vertical.

Elbow-up branch requires `j1 > j2` (upper arm aimed higher than forearm).

## Joint limits

```python
# degrees
J0_LIMITS = (-90,   90)   # base, 0 = straight forward
J1_LIMITS = (  0,  135)   # upper-arm absolute angle from horizontal
J2_LIMITS = (-135,  90)   # forearm absolute angle from horizontal
J3_LIMITS = (-90,   90)   # wrist
# Plus a coupled constraint (parallelogram cannot fold through itself):
#   j2 > 2*j1 - 180     (in the legacy elbow-bend convention this was j1+j2 < 180)
```

## PCA9685 channel map

```python
CHANNELS = {
    "J0": 0,   # base
    "J1": 1,   # shoulder
    "J2": 2,   # elbow
    "J3": 3,   # wrist
    "PUMP":    4,  # reserved, stub for now
    "GRIPPER": 5,  # reserved, stub for now
}
```

PCA9685 at I²C address `0x40`, 50 Hz PWM, pulse widths roughly 500–2500 μs for 0–180°. Per-servo calibration lives in `SERVO_CALIBRATION` in `config.py`:

```python
SERVO_CALIBRATION = {
    0: {"min_us": 500, "max_us": 2500, "zero_deg": 90, "direction": +1},
    1: {"min_us": 500, "max_us": 2500, "zero_deg": 90, "direction": +1},
    2: {"min_us": 500, "max_us": 2500, "zero_deg": 90, "direction": +1},
    3: {"min_us": 500, "max_us": 2500, "zero_deg": 90, "direction": +1},
}
```

Tune these on real hardware. Sim uses identity calibration.

## Inverse kinematics — canonical derivation

Given target `(x, y, z)` in mm and wrist orientation `wrist_deg`:

1. **Base angle:** `θ0 = atan2(y, x)`
2. **Reduce to 2D plane:**
   - `r = sqrt(x² + y²) - L_TOOL`
   - `z' = z - H_BASE`
3. **2-link planar IK** on `(r, z')`:
   - `d² = r² + z'²`
   - `cos_alpha = (L1² + L2² - d²) / (2·L1·L2)` → interior elbow angle α
   - `cos_beta  = (L1² + d² - L2²) / (2·L1·sqrt(d²))` → shoulder offset β
   - `θ1 = atan2(z', r) + β` → upper-arm absolute angle (elbow-up)
   - `θ2 = θ1 + α − π` → forearm absolute angle (parallel-linkage convention)
   - **Elbow-up branch only** — use `acos` with positive sqrt.
4. Map `(θ0, θ1, θ2, wrist_deg)` to servo angles via `SERVO_CALIBRATION`.
5. Raise `WorkspaceError` if `d > L1 + L2` or `d < |L1 − L2|`. Raise `JointLimitError` if any individual or coupled joint limit (`j2 > 2·j1 − 180`) is violated.

**Forward kinematics** mirrors this and is needed for the simulator + verification. Property test:

```python
@given(reachable_point())
def test_fk_ik_roundtrip(p):
    angles = inverse_kinematics(p)
    p2 = forward_kinematics(angles)
    assert distance(p, p2) < 0.1  # mm
```

## Architecture — three layers, strict separation

```
┌─────────────────────────────────────────────┐
│  cli.py  /  server.py  /  examples/         │  ← user-facing
├─────────────────────────────────────────────┤
│  arm.py — UArm class, threading, recording  │  ← high-level
├─────────────────────────────────────────────┤
│  hardware.py — ServoBus, PCA9685, Simulated │  ← driver
└─────────────────────────────────────────────┘
        ↑
   kinematics.py — pure functions, no I/O
   config.py     — constants only
```

- `kinematics.py` is **pure functions**. No I/O, no state. Easy to property-test.
- `hardware.py` exposes a `ServoBus` protocol. `PCA9685Bus` and `SimulatedBus` implement it. Factory `make_bus()` reads `UARM_MODE`.
- `arm.py` owns the `UArm` class, threads, recording state. Talks only to `ServoBus` via the protocol.
- `cli.py` and `server.py` are thin shells over `UArm`.

## Simulation realism requirements

`SimulatedBus` must feel like a real arm so UI behavior maps to hardware behavior:
- Max angular velocity (default 180°/s) — `set_angle` returns immediately, current angle slews toward target
- Background thread updates at ~50 Hz
- Position callbacks fire during the slew, not just at the end
- Optional ±0.5° jitter mode for stress-testing

## Build phases

Stop at each checkpoint. Run tests. Show output. Wait for "go" before continuing.

| Phase | Scope | Done when |
|---|---|---|
| **1** | `config.py`, `kinematics.py`, tests, `docs/walkthroughs/phase1.md` | `uv run pytest tests/test_kinematics.py -v` all green; walkthrough committed |
| **2** | `hardware.py` (sim only), `arm.py`, `cli.py` | `uarm goto 200 0 50` reaches target in sim; `uarm shell` works; recording/replay end-to-end |
| **3** | `server.py` + 3D viz (sim only, read-only) | FastAPI runs, WebSocket streams sim state, 3D arm animates as the CLI drives it |
| **4** | Web UI controls | Joint sliders, Cartesian jog, go-to-position form, teach/replay panel — all driving the sim |
| **5** | `PCA9685Bus`, README hardware setup | Imports lazy; mocked tests pass; no hardware actually driven yet |
| **6** | Stretch: calibration wizard, workspace viz, soft-limit toasts | — |

**Rationale for the order:** the 3D viz is a debugging tool, not a feature. Without a real arm to look at, watching the sim move in 3D is the only way to catch IK bugs that don't show up as numeric test failures (wrong elbow branch, base rotation sign flip, calibration sign errors). Build it before any UI controls — Phase 3 is read-only, just the viz + WebSocket animating from CLI commands. Controls come in Phase 4. Hardware comes last, after the math is visually verified.

## File layout

```
uarm-suite/
├── CLAUDE.md                  ← this file
├── pyproject.toml             (uv)
├── README.md
├── config.py
├── kinematics.py
├── hardware.py
├── arm.py
├── cli.py
├── server.py                  (Phase 3+)
├── static/                    (Phase 3+)
│   ├── index.html
│   ├── viz.js                 (Phase 3 — Three.js arm rendering)
│   ├── app.js                 (Phase 4 — control panels)
│   └── style.css
├── tests/
│   ├── test_kinematics.py
│   ├── test_arm.py
│   └── test_cli.py
├── examples/
│   ├── draw_square.py
│   └── tic_tac_toe.py         (placeholder)
└── recordings/                (gitignored)
```

## What NOT to do

- No Docker, no microservices — single Python process.
- No frontend build step. Vanilla JS + CDN Three.js.
- No auth, no users, no database.
- Don't depend on the official uArm Python SDK.
- Don't run hardware-touching code without my explicit go-ahead.

## Honesty rules

- When uncertain about a fact (link lengths, PCA9685 registers, servo behavior), say so. Web-search primary sources or ask. Don't guess.
- When I say "I tested it on the Pi," believe me. Otherwise, hardware is untested.
- If you find a bug in a previous phase while working on a later one, stop and tell me — don't paper over it.
- If geometry constants here look wrong based on what you find, push back with reasoning. I can re-measure.

## Session kickoff checklist

When starting a fresh session:
1. Read this file.
2. Read the most recent commit message to know where we are in the phase plan.
3. Run `uv run pytest -v` to confirm the current state passes.
4. Ask me what we're doing today before writing any code.