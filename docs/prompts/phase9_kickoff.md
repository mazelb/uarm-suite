# Phase 9 kickoff prompt — Hardware bring-up (pen on paper)

## Where we are

Phases 1–8C are committed. The suite is **code-complete in sim**: 181 tests
passing, ruff clean.

- Full IK/FK, sim + mock + hardware buses, CLI, FastAPI server, 3D viz
- Activities: tic-tac-toe (interactive), draw-shapes, draw-text (runnable)
- **8A** — pen-down Z calibration (`drawing.json`, `uarm pen` CLI) + dry-run jog
- **8B** — `UArm.move_linear`: straight-line Cartesian motion at a feed rate
  (mm/s), midpoint-validated before any motion; feeds persisted and plumbed
  through every drawing path (draw at `feed`, travel at `travel_feed`,
  gentle pen lowering)
- **Pen panel** — pen geometry, feeds, and the grid dry-run from the browser;
  browser pen calibration = Z jog buttons + "Use current Z" + Save
- **8C** — draw-text with a built-in single-stroke vector font

Maz has the hardware ready: Pi 4 + PCA9685 + the arm. **Nothing has ever run
on it.** Phase 9 is wiring, calibration, and the first ink on paper —
done live with Maz at the arm, walkthrough-style, not autonomously.

## Order of operations (agreed in the 8A walkthrough)

0. **Mock rehearsal on the dev box** (`UARM_MODE=mock`): exercises the real
   PCA9685 code path with no Pi; `UARM_MOCK_VERBOSE=1` prints servo writes.
1. **Wiring + smoke test**: PCA9685 at I²C `0x40`, channels J0–J3 per
   `config.CHANNELS`, external 5–6 V servo supply (never the Pi's 5 V rail),
   common ground. `i2cdetect -y 1` shows `40` before anything moves.
2. **First power-on**: `UARM_MODE=hardware uarm home` — slow-home at 30°/s is
   the very first motion (CLAUDE.md rule 7). Hands clear.
3. **Servo calibration** (`calibration.json`, Phase 6 wizard in the web UI):
   zero offsets + directions until commanded joint angles match reality.
   Verify with `uarm where` and known poses before trusting IK.
4. **Geometry re-measure** if needed: `H_BASE`, `L1`, `L2`, `L_TOOL` in
   `config.py` are estimates; wrong values show up as positions that drift
   with reach. Update + re-run the FK/IK property tests.
5. **Pen mount + pen-down Z**: mount the pen, then `uarm pen calibrate` (or
   the browser flow) to find `table_z` for that pen. Label it.
6. **Grid dry-run**: jog-corners on real paper before any stroke.
7. **First ink**: draw-shapes square, then tune `feed` / `travel_feed` for
   clean lines (`uarm pen set --feed …` between scribbles — that's all 8B
   tuning is). Watch for: skipped ink (too fast), blobbing at vertices
   (pen-down feed too slow), dragging (table_z too deep — it has no
   compliance, the Z *is* the pressure).
8. **The goal**: a full tic-tac-toe game on paper against a human.

## Hard rules that bind hardest here

- **Announce-then-run** (rule 8): before any command that moves the arm under
  power, state what runs and how the arm will physically move. Sim/mock run
  freely.
- **Don't fabricate hardware results** (rule 9): Maz runs the Pi or watches
  it run; report only observed output. Everything in phases 5–8 is
  sim/mock-validated only until this session says otherwise.
- **No silent clamping** (rule 5): if the real workspace turns out smaller
  than the configured one, fix constants — don't widen tolerances.

## Lessons from Phase 8 (sim half)

1. **Feed (mm/s, Cartesian) and joint speed (°/s) are different axes of
   control.** `move_linear` paces 2 mm IK steps with deadline sleeps and a
   per-step `set_speed`, clamped by `DEFAULT_DEG_PER_SEC`. Both buses slew at
   50 Hz the same way, so pacing should transfer to hardware unchanged — but
   verify smoothness on real servos before tuning values.
2. **The whole-path validation invariant now covers midpoints.** `move_linear`
   solves IK for every interpolated step before any motion. Keep this when
   touching motion code — a half-drawn stroke on paper is the failure mode
   this exists to prevent.
3. **Tests stay fast via monkeypatched module constants**:
   `arm.*_DEG_PER_SEC`, `activities._draw.DRAW/TRAVEL_FEED_MM_S`,
   `server.TRAVEL_FEED_MM_S` → huge values. New hardware-session code must
   keep `uv run pytest -q` green with no hardware attached.
4. **Partial REST updates with nullable semantics**: `POST /api/pen` uses
   pydantic `model_fields_set` so "absent" ≠ "explicit null" (null clears a
   feed override; null on required geometry is ignored). Reuse the pattern.
5. **drawing.json is per-machine/per-pen and gitignored** — the Pi gets its
   own via calibration, never copied from the dev box. `feed`/`travel_feed`
   `null` means suite defaults (`config.DRAW_FEED_MM_S = 40`,
   `TRAVEL_FEED_MM_S = 120` — placeholders awaiting paper).
6. **WSL2 mirrors Windows ports**: Home Assistant (Docker) owns 8123 on this
   machine and answers 404s that look like a broken server. Stick to 8000,
   and suspect host port squatters when an endpoint 404s unexpectedly.
7. **Activity options coerce through `cli._coerce` / pydantic extra-allow**,
   and `ValueError` from bad options is a clean 422/CLI error as of 8C.
   New activities get this for free by raising `ValueError` early.

## Test plan for phase 9

- No new sim tests required, but any code change made at the arm (calibration
  persistence tweaks, config updates) re-runs `uv run pytest -q` before commit.
- The real "tests" are the walkthrough checkpoints above, observed by Maz.
- Capture tuned values (servo calibration, geometry, table_z, feeds) in the
  phase 9 walkthrough as the reference for re-rigging the pen later.
