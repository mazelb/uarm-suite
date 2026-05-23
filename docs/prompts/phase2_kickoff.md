# uArm Suite — Phase 2 kickoff prompt (fresh session)

Paste the section below the divider into a new session. It assumes the
session will follow the standard kickoff checklist in `CLAUDE.md` (read it,
check the last commit, run the test suite, ask before coding).

---

We're continuing work on the uArm Swift control suite. Start by reading
`CLAUDE.md` end-to-end — it has all the geometry constants, the IK
derivation, joint limit conventions, file-layout plan, hard rules, and the
six-phase roadmap. Then run `uv run pytest -v` to confirm the current state
is green before writing any code. Also skim `docs/walkthroughs/phase1.md`
so you know what manual-validation surface area already exists — you'll
extend the same pattern for Phase 2.

## Where we are

**Phase 1 is complete and committed.** The repo currently contains:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml          uv project; package=false; py311+; pytest+hypothesis+ruff
├── conftest.py             adds repo root to sys.path for the flat layout
├── config.py               H_BASE/L1/L2/L_TOOL, joint limits, channel map, SERVO_CALIBRATION
├── kinematics.py           forward_kinematics, inverse_kinematics (elbow-up only),
│                           WorkspaceError, JointLimitError, in_workspace,
│                           JointAngles + Position NamedTuples
└── tests/test_kinematics.py  19 tests, all green (incl. hypothesis FK/IK round-trip)
```

Phase 1 left **two unresolved questions** that you should surface to Maz
before starting Phase 2 work that depends on them. Do not silently make
assumptions — ask:

1. **The `J1 + J2 < 180°` parallelogram constraint clips the documented
   workspace.** With IK exactly as CLAUDE.md specifies (logical joint
   convention: `j1` = shoulder elevation above horizontal, `j2` = elbow
   bend from straight), the central target `(200, 0, 80)` already yields
   `j1≈67°, j2≈123°, sum≈190°` and is rejected by `JointLimitError`.
   Several reasonable mid-envelope targets do the same. Two plausible
   readings:
     - the constraint belongs on *servo* angles (post-`SERVO_CALIBRATION`
       mapping), not on the logical IK output; or
     - the logical `J2` upper bound needs to drop (or the `j2` convention
       needs to change to "forearm angle from horizontal" = `θ1 - (π-α)`).
   `tests/test_kinematics.py::test_ik_joint_limit_violation_raises` pins
   the current strict behavior — changing it is a deliberate decision.

2. **IK mirror solutions in the −X hemisphere.** When `j1 > 90°` (arm
   swings past vertical), the wrist crosses into −X and the round-trip
   recovers a mirror configuration via `j0 = ±180°`. Such targets are
   outside the `j0 ∈ [−90°, 90°]` limit anyway, so the property-test
   strategy in `tests/test_kinematics.py::_joint_strategy` caps `j1` at
   90° to avoid the ambiguity. Flagging in case Maz wants IK to attempt
   the mirror solution someday.

## What to do in Phase 2

Per CLAUDE.md, Phase 2 is "Simulated arm + CLI." Done when:

- `uv run uarm goto 200 0 50` reaches the target in sim and prints the
  reached position.
- `uv run uarm shell` opens a REPL with a live `UArm` instance bound as
  `arm`.
- Recording and replay work end-to-end against `SimulatedBus`.
- All tests green (`uv run pytest`).

Modules to build (the architecture diagram in CLAUDE.md is canonical —
follow the layering strictly):

- **`hardware.py`** — `ServoBus` protocol with `set_angle(channel,
  degrees) / get_angle(channel) / disable(channel)`, plus the
  `SimulatedBus` implementation. `SimulatedBus` must slew current angles
  toward targets at a configurable max angular velocity (default
  `DEFAULT_DEG_PER_SEC = 180°/s` from config.py), tick at
  `SIM_UPDATE_HZ = 50 Hz` on a background thread, fire position
  callbacks during the slew (not just at the end), record every command
  for later inspection, and support an optional `±0.5°` jitter mode.
  Include the `PCA9685Bus` *class stub* with a lazy hardware import
  guarded so that importing `hardware` on a dev machine without the
  Adafruit libraries does not fail — but defer the real PCA9685
  implementation to Phase 5. Factory `make_bus()` reads `UARM_MODE`
  (default `sim`).

- **`arm.py`** — `UArm` class wrapping the bus, with
  `connect/disconnect/home`, `set_joint_angles`, `set_position` (uses
  `inverse_kinematics`), `get_position` (uses `forward_kinematics`),
  `move_along(path)`, recording (`record_start/record_stop`), replay
  (`replay(recording, speed_factor=1.0)`), and stubs for `set_pump` /
  `set_gripper` (channels 4 and 5 in `config.CHANNELS`) that log the
  call. Long moves run in a background thread; expose a position
  callback for the eventual UI. Slow-home at startup at
  `SLOW_HOME_DEG_PER_SEC = 30°/s` — never snap. Surface every
  `WorkspaceError` / `JointLimitError` up to the caller — no silent
  clamping.

- **`cli.py`** — Typer (preferred over Click; pull it in via
  `uv add typer`). Commands per CLAUDE.md: `uarm home`,
  `uarm goto X Y Z [--wrist DEG] [--speed N]`,
  `uarm joints J0 J1 J2 J3`, `uarm where`, `uarm record NAME`,
  `uarm play NAME [--speed-factor F]`, `uarm list`, `uarm shell`.
  Register `uarm` as a project script in `pyproject.toml`'s
  `[project.scripts]` so `uv run uarm <cmd>` works (note: pyproject is
  currently `package = false` — flipping that on requires either
  promoting cli.py into a small package directory or using a different
  install path; pick the lighter option and explain it).

- **Recordings** stored in `recordings/<name>.json` (the directory is
  gitignored — verify or add to `.gitignore`).

- **Tests:** `tests/test_arm.py` (UArm against `SimulatedBus`: home,
  goto, joints, move_along, get_position round-trip, recording/replay
  fidelity, position-callback fires during slew, errors propagate) and
  `tests/test_cli.py` (Typer `CliRunner` invocations of each command
  against a sim instance). Property test for the slew model is nice if
  it's quick.

## Working agreement (reminder; full version in CLAUDE.md)

- `uv` for deps (`uv add`, `uv run`). `pytest` after every meaningful
  change. `ruff check --fix .` and `ruff format .` before declaring the
  phase done.
- **Ask before running anything that touches hardware paths** — `/dev/i2c-*`,
  real GPIO, or imports of `board`/`busio`. Pure sim is fine to run freely.
- **`UARM_MODE` defaults to `sim`.** Hardware path is opt-in and untested
  this phase.
- Type-hint everything. No silent clamping. Joint angles ≠ servo angles —
  keep the two frames strictly separated.
- **Stop at the end of Phase 2.** Show test output. Wait for Maz's "go"
  before starting Phase 3 (3D viz).
- One commit at the end with a clear message like
  `Phase 2: sim bus + UArm class + CLI`.
- **Walkthrough is part of the phase**, not optional polish. Write
  `docs/walkthroughs/phase2.md` modeled on `phase1.md`: exact bash
  commands, exact expected outputs (sample CLI sessions, recording JSON
  shape, REPL transcripts), and a "what you should NOT see yet" section
  for behavior that's still deferred. Include it in the same commit. The
  same convention applies to every subsequent phase — extend `CLAUDE.md`'s
  build-phases table for Phase 3 onward to keep that explicit.
