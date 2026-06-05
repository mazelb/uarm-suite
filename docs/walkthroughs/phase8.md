# Phase 8A walkthrough — Pen-down Z calibration + dry-run jog

Step-by-step manual validation for Phase 8A. Everything here runs in **sim mode**
(`UARM_MODE=sim`, the default) — no hardware required. The same commands are
what you'll run on the Pi later to find the real pen height; in sim they
rehearse the flow and prove the math/persistence.

## What 8A delivers

The arm has no wrist pitch, so the commanded tool-tip Z **is** the pen contact
height. That height (`table_z`) is the one physical unknown every drawing path
depends on, and nothing persisted it before. 8A adds:

- `drawing.py` — `DrawingConfig` (`table_z`, `pen_up`, `wrist`, `pen_label`)
  persisted to `drawing.json` (gitignored, per-machine/per-pen).
- `uarm pen` CLI: `show`, `set`, `calibrate` (interactive Z jog), `jog-corners`
  (dry-run that visits the grid footprint at pen-up height).
- Drawing activities (`tic-tac-toe`, `draw-shapes`) now **auto-load** the
  persisted height; `-o table_z=…` still overrides.

## Prerequisites

- Phases 1-7 committed.
- `uv run pytest -q` shows **155 tests passing**.
- `uv run ruff check .` is clean.
- If `uarm pen …` fails with `ModuleNotFoundError: No module named 'drawing'`,
  refresh the editable install once: `uv pip install -e .` (the new module was
  added to `pyproject.toml`).

## 1. Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

**Expected:** `155 passed`, `All checks passed!`.

## 2. Show the default config (no file yet)

```bash
rm -f drawing.json
uv run uarm pen show
```

**Expected:**

```
table_z  =    0.0 mm   (pen-down contact height)
pen_up   =   20.0 mm   (travel clearance)
pen_up_z =   20.0 mm
wrist    =    0.0 deg
pen      = (unlabeled)
(no drawing.json yet — showing defaults)
```

With no `drawing.json`, the defaults match the old hardcoded values, so sim
behaviour is unchanged from Phase 7.

## 3. Set values without moving

```bash
uv run uarm pen set --table-z -30 --pen-up 15 --label "fine Sharpie"
```

**Expected:** writes `drawing.json` and echoes the new config:

```
Saved to drawing.json.
table_z  =  -30.0 mm   (pen-down contact height)
pen_up   =   15.0 mm   (travel clearance)
pen_up_z =  -15.0 mm
wrist    =    0.0 deg
pen      = fine Sharpie
(saved at drawing.json)
```

## 4. Dry-run: jog the grid corners (pen stays up)

This is the **placement check** — confirm the grid footprint lands on the paper
*before* drawing anything. The pen never lowers below `pen_up_z`.

```bash
printf '\n\n\n\n' | uv run uarm pen jog-corners
```

(Interactively, just press Enter between corners instead of piping.)

**Expected:** slow-homes, then visits all four outer corners of the default
250/0, cell-40 grid:

```
Jogging the 4 grid corners at pen-up Z -15.0 mm (pen never lowers).
Slow-homing to a safe pose…
  corner 1/4 → (190, -60)
    [Enter] for next corner:   corner 2/4 → (190, 60)
    [Enter] for next corner:   corner 3/4 → (310, 60)
    [Enter] for next corner:   corner 4/4 → (310, -60)
    [Enter] for next corner: Done — all four corners reached.
```

It **refuses up front** if any corner is out of reach — nothing moves:

```bash
uv run uarm pen jog-corners --cell 120
```

**Expected** (exit code 1):

```
Error: 2 grid corner(s) unreachable at pen-up Z -15.0: (430, 180), (430, -180). Move/shrink the grid.
```

## 5. Interactive pen-down Z calibration

On hardware: lower the pen step by step until it *just* touches the paper, then
save. In sim it's the same flow (the arm slews; nothing touches paper).

```bash
uv run uarm pen calibrate
```

It hovers the pen over `(250, 0)` at the current `pen_up_z`, then loops:

```
Pen-down Z calibration.
Hovering the pen at (250, 0); jog Z until it just kisses the paper.
Commands: [Enter] lower by step · 'u' raise by step · 'step <mm>' change step
          's' save table_z here · 'q' quit without saving
Slow-homing to a safe pose…
z=-15.0mm step=2.0:
```

**Test:**
1. Press **Enter** to lower by `step` mm (here 2). The prompt updates to a lower Z.
2. Type `step 0.5` then Enter to take finer bites near contact.
3. Type `u` to raise if you overshoot.
4. Type `s` to save: `Saved table_z = … mm to drawing.json.`
5. `q` quits without saving.

Each step is workspace-checked *before* motion — an out-of-reach Z is refused
(`z=… is outside the workspace — staying at …`) rather than faulting.

## 6. Activities pick up the saved height

With a `drawing.json` present (from step 3/5), drawing activities default to it:

```bash
uv run uarm pen set --table-z -30 --pen-up 15
uv run uarm activity run draw-shapes -o shape=square -o size=40
```

The square is drawn with pen-down Z = -30 and pen-up Z = -15 (visible in the
3D viz if the server is running). Override per-run with `-o table_z=…`.

## 7. Servo calibration (order of operations on the Pi)

`SERVO_CALIBRATION` (zero offsets + directions, `calibration.json`) is tuned
with the existing Phase 6 wizard in the web UI — no new code in 8A. Recommended
order when you bring up the real arm:

1. **Servo calibration first** (`calibration.json`): get each joint's zero and
   direction right so commanded joint angles match reality. Verify with
   `uarm where` / jogging to known poses.
2. **Re-measure geometry** if needed (`H_BASE`, `L1`, `L2`, `L_TOOL` in
   `config.py`) — the current values are estimates.
3. **Pen-down Z last** (`drawing.json`, this walkthrough): with kinematics
   trustworthy, find the pen contact height for the mounted pen.

## What you should NOT see yet (deferred)

- **No pen pressure / feed-rate tuning.** Per-stroke speed for clean lines is
  Phase 8B; `pen calibrate` only finds contact height.
- **No real hardware results here.** These steps are sim-validated. The contact
  height found in sim is meaningless on paper — re-run `pen calibrate` on the Pi
  with the real pen mounted (announce-then-run per CLAUDE.md rule 8).
- **No wrist-pitch DOF.** The pen still points along the arm plane; the physical
  pen offset is entirely absorbed into `table_z`. There is no new orientation
  control.
- **No web-UI pen panel.** Calibration is CLI-only for now.
