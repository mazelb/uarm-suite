# Phase 8 kickoff prompt — Hardware drawing bring-up + activity polish

## Where we are

Phases 1-7 are committed. The suite is feature-complete in **sim**:
- Full IK/FK, sim bus, PCA9685 hardware bus (mocked tests only)
- CLI + FastAPI server + 3D web UI with controls
- Recording/replay, calibration wizard, workspace viz, soft-limit toasts
- **Activities framework** (`activities/`) with auto-discovery, two flavours
  (runnable + interactive), generic server endpoints, CLI `uarm activity`
- **Tic-tac-toe** (unbeatable minimax, web board + terminal game, arm draws
  grid/X/O, celebrate/hang-head) and **draw-shapes** demo activity
- 134 tests passing, ruff clean

Everything in Phase 7 is **sim-validated only**. No pen has touched paper.

## Project motivation

The original goal — a uArm that physically plays tic-tac-toe against a kid — is
implemented in sim. Phase 8 is the bridge to the real arm: make it actually draw.

## What to build (proposed — confirm with Maz before coding)

### 8A: Pen-drawing hardware bring-up
- A documented pen mount + a **pen-down Z calibration** flow: find the table
  contact height for the current pen and persist it (extend `calibration.json`
  or a new `drawing.json`). The model has no wrist pitch, so the commanded
  tool-tip Z maps to pen tip through this offset — this is the key unknown.
- A **dry-run / jog-to-corner** helper so Maz can verify the grid lands on the
  paper before any stroke (move to each grid corner at pen-up height).
- Tune `SERVO_CALIBRATION` against the real servos (zero offsets + directions);
  the existing calibration wizard already writes these.

### 8B: Physical robustness
- Feed rate / pen pressure tuning for clean lines (speed per stroke).
- Re-validate that real geometry constants (`H_BASE`, `L1`, `L2`, `L_TOOL`)
  match the measured arm — update `config.py` if Maz re-measures.

### 8C: Closing the loop (stretch)
- Sense the human's physical move instead of clicking the web board: a camera +
  simple grid/marker detection, or a tap sensor per cell. Keep it behind the
  `ActivityBase` boundary — activities still talk only through `UArm` plus a new
  input source.

### 8D: More activities (stretch)
- Prove the framework again: e.g. "draw text", "Etch-A-Sketch jog mode", or a
  second game. Each is just a new module in `activities/`.

## Lessons from Phase 7

1. **`runtime_checkable` Protocols with data members break `issubclass()`.**
   `is_interactive()` checks the interactive methods structurally with `hasattr`,
   not `issubclass`. Keep that if you extend the protocol.

2. **Interactive vs runnable was a real architectural fork.** A single blocking
   `run(arm)` can't model a turn-based game that waits on a human. The split —
   runnable activities via `/run`, interactive via `start`/`move`/`state` with a
   single server-held session + lock — is the load-bearing design. New games
   should implement the interactive protocol; new demos the runnable one.

3. **Validate the whole drawing path before moving.** `_draw.validate_reachable`
   checks every point (at both pen-up and pen-down Z) up front and raises
   `WorkspaceError`, so a bad target never half-draws. Phase 8 hardware work must
   keep this invariant — a half-drawn stroke on paper is worse than a clean refusal.

4. **No wrist pitch.** Drawing treats the tool-tip Cartesian target as the pen
   contact point; the physical pen offset is absorbed into Z calibration. 8A's
   calibration flow is exactly this offset. Don't try to add a pitch DOF the arm
   doesn't have.

5. **Keep sim tests fast by faking the arm.** Game-logic and drawing tests use a
   tiny recording `FakeArm` (records `set_position` calls) instead of slewing the
   real `SimulatedBus`; server/CLI tests bump `*_DEG_PER_SEC` to ~10000. Real
   slewing at 180°/s makes a full game take many seconds.

6. **Typer option defaults trip ruff B008.** Use the `Annotated[...]` form for
   repeatable options (`option: Annotated[list[str] | None, typer.Option(...)]`).

7. **Activities are a package now** — declared in `[tool.setuptools] packages`.
   New activity modules are picked up by `discover()` automatically.

## Key constraints (unchanged)

- Activities talk to the arm only through `UArm`; never import hardware libs.
- Hardware-touching code needs Maz's explicit go-ahead (CLAUDE.md rule 8). Phase
  8 is the first phase that genuinely drives `/dev/i2c-*` and moves real servos.
- Don't fabricate hardware results — Maz runs the Pi and reports what happened.
- One commit per sub-phase; ship `docs/walkthroughs/phase8.md` in the same commit.

## Test plan

- Calibration persistence round-trips (write → read → values match).
- Grid-corner jog helper produces reachable pen-up targets.
- Any new sensing/input path: unit-test the detection logic on fixtures, not live
  hardware.
- Keep the sim path green: `uv run pytest -q` must still pass with no hardware.
