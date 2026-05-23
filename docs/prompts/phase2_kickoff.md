# uArm Suite — Phase 2 kickoff prompt (fresh session)

Paste everything below the divider into a new session. It assumes the standard
kickoff checklist in `CLAUDE.md` (read it, check the last commit, run the test
suite, ask before coding).

---

We're continuing work on the uArm Swift control suite. Start by reading
`CLAUDE.md` end-to-end — geometry constants, the IK derivation, the j1/j2
convention (both segments use **absolute angles from horizontal**, not elbow
bend), joint limits and the parallelogram coupling `j2 > 2·j1 − 180°`, the
hard rules, and the six-phase roadmap. Then read
`docs/walkthroughs/phase1.md` so you know the manual-validation pattern
you'll extend. Confirm green state before writing any code:

```bash
git log --oneline -5
uv run pytest -v
uv run ruff check .
```

You should see one commit (`Phase 1: kinematics + config + tests`),
20 tests passing, lint clean.

## Where we are

Phase 1 is committed. Repo contents:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml          uv project; package=false; py311+; pytest+hypothesis+ruff
├── conftest.py             adds repo root to sys.path for the flat layout
├── config.py               H_BASE/L1/L2/L_TOOL, joint limits, channel map,
│                           SERVO_CALIBRATION, parallelogram_floor_deg helper,
│                           SLOW_HOME_DEG_PER_SEC, DEFAULT_DEG_PER_SEC, SIM_UPDATE_HZ
├── kinematics.py           forward_kinematics, inverse_kinematics (elbow-up only),
│                           WorkspaceError, JointLimitError, in_workspace,
│                           JointAngles + Position NamedTuples
├── tests/test_kinematics.py  20 tests including hypothesis FK/IK round-trip
└── docs/walkthroughs/phase1.md
```

**j2 convention you must respect throughout Phase 2:** `j2` is the
**forearm absolute angle from horizontal** (signed). `j2 = 0` is forearm
horizontal; `j2 > 0` is wrist above elbow; `j2 < 0` is wrist below
elbow. Elbow-up requires `j1 > j2`. The parallelogram coupling
constraint is `j2 > 2·j1 − 180°` (use `config.parallelogram_floor_deg`).
Servo angles ≠ joint angles — keep the two frames strictly separated.

**Open flag (not a Phase 2 blocker):** there's a `TODO` in
`kinematics.py` about IK mirror solutions when `j1 > 90°` (wrist crosses
into −X). The property test caps `j1` at 90° to avoid the ambiguity.
Don't try to "fix" it in Phase 2.

## What to do in Phase 2

Per CLAUDE.md, Phase 2 is "Simulated arm + CLI." **Done when:**

- `uv run uarm goto 200 0 50` reaches the target in sim and prints the
  reached position.
- `uv run uarm shell` opens a REPL with a live `UArm` instance bound as
  `arm`.
- Recording and replay work end-to-end against `SimulatedBus`.
- All tests green (`uv run pytest`).
- Walkthrough and build report committed.
- Sub-agent validation (see "Final validation" below) passes.

Modules to build — follow the architecture layering in CLAUDE.md strictly:

### `hardware.py`

- `ServoBus` protocol with at least
  `set_angle(channel: int, degrees: float, *, immediate: bool = False) -> None`,
  `get_angle(channel: int) -> float`,
  `disable(channel: int) -> None`,
  and a way to subscribe to per-tick position updates
  (e.g. `add_listener(callback)` where `callback(snapshot: dict[int, float])`).
- `SimulatedBus` implementation that:
  - Slews current angles toward targets at a configurable
    `max_deg_per_sec` (default `DEFAULT_DEG_PER_SEC = 180.0` from
    `config.py`).
  - Ticks at `SIM_UPDATE_HZ = 50 Hz` on a background daemon thread,
    started on first use and joined on `close()`.
  - Fires position-listener callbacks every tick during the slew, not
    just at the end.
  - Records every command for later inspection (useful in tests).
  - Optional `±0.5°` jitter mode toggleable via constructor flag for
    stress-testing.
  - `immediate=True` snaps the current angle without slewing (used by
    the hardware-mode `disable` path and for tests).
- `PCA9685Bus` **class stub only.** The hardware import must be lazy —
  inside `__init__` or a `_connect` method, **not** at module top. On a
  dev machine without `adafruit_pca9685` installed, `import hardware`
  must succeed. Raise a clear `RuntimeError` if instantiated without
  the libraries. **Do not actually drive any hardware in this phase.**
- Factory `make_bus(mode: str | None = None) -> ServoBus` that reads
  `UARM_MODE` (default `sim`). `mode="hardware"` instantiates
  `PCA9685Bus`.

### `arm.py`

- `UArm` class wrapping a `ServoBus`. Public API:
  - `connect()` / `disconnect()` / context-manager protocol.
  - `home(blocking: bool = True)` — slow-home at
    `SLOW_HOME_DEG_PER_SEC = 30°/s` to a known safe pose
    (suggested: `j0=0, j1=45, j2=−45, j3=0` — clearance above table,
    inside all limits, satisfies parallelogram coupling).
  - `set_joint_angles(j0, j1, j2, j3, *, speed=None, blocking=False)`.
  - `set_position(x, y, z, *, wrist=0.0, speed=None, blocking=False)`.
    Uses `inverse_kinematics`. Surfaces `WorkspaceError` /
    `JointLimitError` from the caller — **no silent clamping**.
  - `get_joint_angles() -> JointAngles`.
  - `get_position() -> Position` — via `forward_kinematics` on the
    current bus angles.
  - `move_along(path: Iterable[tuple[float, float, float]], *, wrist=0.0, speed=None)`
    — sequence of Cartesian points; runs on a background thread.
  - `wait_for_idle(timeout: float | None = None) -> bool`.
  - Position callback hook: `on_position(callback)` where
    `callback(pos: Position)` fires whenever the underlying bus's
    position changes.
  - Recording: `record_start(name: str)`, `record_stop() -> Path`. Each
    sample is `{t, j0, j1, j2, j3}` at a fixed rate (default 20 Hz).
    Persist to `recordings/<name>.json`.
  - Replay: `replay(name_or_path, *, speed_factor: float = 1.0,
    blocking: bool = True)`.
  - `set_pump(on: bool)` / `set_gripper(open_: bool)` — log-only stubs
    that write to the bus channels 4 and 5 (defined in
    `config.CHANNELS`) but do nothing physical. Phase 5 will wire
    these for real.
- Long moves run on a background thread; the main thread must not
  block unless `blocking=True` is passed.

### `cli.py`

- Use **Typer** (`uv add typer`). Commands (per CLAUDE.md):
  - `uarm home`
  - `uarm goto X Y Z [--wrist DEG] [--speed N]`
  - `uarm joints J0 J1 J2 J3 [--speed N]`
  - `uarm where` — print current `(x, y, z)` and joint angles.
  - `uarm record NAME` — record until Ctrl-C, write to
    `recordings/NAME.json`.
  - `uarm play NAME [--speed-factor F]`.
  - `uarm list` — list recordings.
  - `uarm shell` — open a Python REPL with `arm: UArm` already
    connected and bound in the namespace. Use `code.interact` or
    similar.
- Errors from the arm (`WorkspaceError`, `JointLimitError`) print a
  clean message and exit with non-zero status — **don't** swallow them.
- Register the entry point. The repo currently has `package = false`
  in `pyproject.toml`'s `[tool.uv]`, which makes `[project.scripts]`
  not install. Pick the lightest option that lets `uv run uarm <cmd>`
  work and explain the choice in the build report. Two reasonable
  paths:
  - Drop `package = false` and add
    `[project.scripts] uarm = "cli:app"`. Promote the flat layout
    into a tiny package directory if needed.
  - Keep `package = false` and define a project script via
    `[tool.uv.workspace]` / `[project.scripts]` with a `pyproject.toml`
    tweak; explain the trade-off.

### `recordings/`

- Directory created on first record. Already in `.gitignore`.

### Tests

- `tests/test_arm.py`:
  - `UArm` against `SimulatedBus`: home, goto, joints round-trip,
    `get_position` matches what was set, `move_along` visits each
    waypoint, recording/replay fidelity (replayed positions match
    recorded positions to < 0.1 mm), position-callback fires during
    slew (not just at the end), `WorkspaceError` /
    `JointLimitError` propagate, `disconnect` joins the background
    thread.
- `tests/test_cli.py`:
  - Typer `CliRunner` invocations of every command against a sim
    arm. Verify exit codes, stdout snippets, and side-effects on the
    recordings directory (use a tmp path).
- A small property test for the sim slew model (slew time ≈ `|Δangle|
  / speed`) is welcome if it stays under a second or two.

## Working agreement

- `uv` for deps (`uv add`, `uv run`). `pytest` after every meaningful
  change. `ruff check --fix .` and `ruff format .` before declaring
  the phase done.
- **Ask before running anything that touches hardware paths** —
  `/dev/i2c-*`, real GPIO, or imports of `board`/`busio`. Pure sim is
  fine to run freely.
- **`UARM_MODE` defaults to `sim`.** Hardware path stays untested
  this phase.
- Type-hint everything. No silent clamping. Joint angles ≠ servo
  angles.
- One commit at the end with a message like
  `Phase 2: sim bus + UArm class + CLI`.

## Deliverables required at the end of Phase 2

### 1. `docs/walkthroughs/phase2.md`

Model on `docs/walkthroughs/phase1.md`: exact bash commands, exact
expected outputs (CLI sessions, recording JSON shape, REPL
transcripts), and a "What you should NOT see yet" section listing
Phase 3+ behavior. Cover at minimum:

- `uv run pytest -v` (all tests green, current count).
- `uv run uarm where` (idle pose).
- `uv run uarm home` (slow-home behavior; what changes in
  `uarm where`).
- `uv run uarm goto 200 0 50` (success path + position printed).
- `uv run uarm goto 200 0 80` (parallelogram-coupling failure path —
  non-zero exit + clean error).
- `uv run uarm goto 500 0 80` (out-of-reach failure path).
- `uv run uarm joints 0 60 -30 0` (joint-space move).
- `uv run uarm record demo` → Ctrl-C → `uv run uarm list` →
  `uv run uarm play demo`.
- `uv run uarm shell` (sample REPL transcript).
- Show the JSON shape of a `recordings/<name>.json` file (one or two
  sample frames).

### 2. `docs/reports/phase2.md`

A short build report (no marketing copy, no emoji). Sections:

- **What was built.** Bullet list of modules, public
  classes/functions, and tests added.
- **Test results.** Numbers from `pytest`, `ruff check`,
  `ruff format`.
- **Drifts from the plan.** Anything in this kickoff that you
  changed during the session and why. Examples that count as drift:
  - Different home pose than suggested.
  - Different recording format than `{t, j0, j1, j2, j3}` JSON.
  - Different packaging approach to register the `uarm` entry point.
  - Renaming or adding public API beyond what's listed above.
  Be explicit: "I picked X over Y because Z."
- **Open questions / deferred.** Anything you noticed that should
  land in Phase 3+ or that needs Maz's input. Include a re-read of
  the Phase 1 mirror-IK `TODO` if you touched anything near it.
- **Commit:** the single Phase 2 commit hash.

### 3. Phase 2 commit

One commit, all of the above included. Message:
`Phase 2: sim bus + UArm class + CLI`.

## Final validation — sub-agent test pass

After everything above is committed locally, spawn **three sub-agents
in parallel** via a single message with three `Agent` tool calls.
Each is read-only — they must not modify files. Wait for all three
results, then summarize for Maz.

### Agent A — Test & lint runner (subagent_type: `general-purpose`)

```
You are validating Phase 2 of the uArm Swift control suite.

Run, in order:
  1. uv run pytest -v
  2. uv run ruff check .
  3. uv run ruff format --check .

Report:
  - Total tests collected, passed, failed, skipped, xfailed.
  - Any hypothesis flaky-test warnings.
  - Any ruff findings (file:line + rule).
  - Any format diff (file list only).

Do not fix anything. Under 300 words. Plain text, no emoji.
```

### Agent B — Walkthrough verifier (subagent_type: `general-purpose`)

```
You are validating Phase 2 of the uArm Swift control suite by
executing the manual walkthrough.

Open docs/walkthroughs/phase2.md. For every fenced bash block in
order, run the command verbatim and capture stdout+stderr. Compare
the actual output against the documented expected output line by
line. Skip steps that require interactive Ctrl-C (note them as
"manual: skipped" and execute a programmatic equivalent if the
walkthrough provides one).

For `uarm shell`, send `arm.get_position()` then `exit()` via stdin
and report the REPL transcript.

Report:
  - For each step: PASS, DIVERGE (with diff), or SKIPPED (with
    reason).
  - Total step count and PASS count.

Do not modify any files. Do not retry failed commands. Under 500
words.
```

### Agent C — Hard-rules auditor (subagent_type: `general-purpose`)

```
You are auditing Phase 2 of the uArm Swift control suite against
the hard rules in CLAUDE.md.

Read CLAUDE.md "Hard rules" section (rules 1-10) and "Honesty
rules" section. Then read hardware.py, arm.py, cli.py, and grep
through tests/ for any test that might violate the rules.

For each rule, report PASS or FAIL with file:line evidence.

Specifically verify:
  - Rule 1: no top-level imports of board, busio, adafruit_pca9685,
    adafruit_servokit anywhere outside the PCA9685Bus class body
    (use grep -n).
  - Rule 2: make_bus() reads UARM_MODE and defaults to sim.
  - Rule 3: SERVO_CALIBRATION is only applied in the hardware
    layer; arm.py and cli.py operate in logical joint angles.
  - Rule 4: kinematics.py still uses the elbow-up branch only
    (math.acos with positive root, no math.copysign games).
  - Rule 5: WorkspaceError and JointLimitError are raised, not
    swallowed. CLI prints them and exits non-zero.
  - Rule 6: set_position and move_along return without blocking
    unless blocking=True is passed.
  - Rule 7: home() uses SLOW_HOME_DEG_PER_SEC.
  - Rule 10: no import of uarm.* or uArm SDK packages.

Do not modify any files. Under 400 words.
```

After all three return, write a single status block to the chat:

```
Phase 2 validation
  Agent A (tests/lint):  PASS / FAIL — <one line>
  Agent B (walkthrough): PASS / FAIL — <one line>
  Agent C (hard rules):  PASS / FAIL — <one line>
```

If any agent flags issues, **stop and surface them to Maz before
attempting fixes.** Don't paper over. If everything passes, say so and
wait for Maz's "go" before starting Phase 3.

---

## Stop conditions

- Stop and ask Maz if:
  - Any hard-rule audit fails.
  - You find a regression in Phase 1 code.
  - You're about to deviate materially from the plan (e.g. a
    different recording format, a different packaging approach).
  - You want to add a dep beyond `typer`.
- **Do not** start Phase 3 (3D viz). Stop after the sub-agent
  validation block, regardless of outcome.
